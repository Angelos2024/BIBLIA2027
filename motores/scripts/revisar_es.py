# -*- coding: utf-8 -*-
"""revisar_es.py — MOTOR UNIFICADO de revisión del campo español (`es`).

Consolida en un solo motor local, sin dependencias de chat, todo lo que antes
estaba disperso en varios scripts:

  · revisar_bloque_es.py   → malformaciones, repetidos, recorridos, fuera-de-canon
  · spanish_rules.py       → vacíos, concordancia artículo/posesivo, truncados
  · es_latam_neutral.py    → español peninsular → latino  (se REUTILIZA como librería)
  · (revisión manual)      → "su sus"/dobles por render, cut-short, transliteración

Detecta las categorías de CATEGORIES y, con --apply, corrige SOLO las clases
deterministas y seguras (el conjunto AUTOFIX). Hoy AUTOFIX =
{CANON, PENINSULAR, CONSTRUCT, POSES, CONCORD, PRON}:
  · CANON       glosa contra el canon unánime de la fuente.
  · PENINSULAR  España→Latino.
  · CONSTRUCT   constructo sin nexo genitivo → añade «de» (Opción B: N1 recibe
                «de», N2 intacto).  OJO: no consulta tus estadísticas de estilo;
                si históricamente escribes el constructo SIN «de», choca con
                ESTILO (ver AVISO más abajo).
  · POSES       posesivos apilados: limpia el sufijo redundante ("su sus hijos"→
                "sus hijos") Y quita el posesivo LARGO/tónico incrustado en la raíz
                del sustantivo ("mío señor"+suf "mi" → "señor" → "mi señor").
  · CONCORD     número del sufijo posesivo (su→sus ante plural) Y concordancia
                de ARTÍCULO (el/la/los/las) con el sustantivo español, cuando el
                género/número es SEGURO (excepciones tribu/maná/día/mano/agua…
                tabuladas). «el tienda»→«la tienda».
  · TRANSLIT    mayúscula de nombre propio/gentilicio en minúscula (una palabra):
                «cananeos»→«Cananeos». El resto de TRANSLIT (sin glosa, [EN:],
                hebreo, topónimo compuesto) queda en reporte.
  · PRON        quita el pronombre redundante de raíces preposicionales / idiom הנה.
Se REPORTAN (sin auto-aplicar) las que requieren criterio léxico: MORPH_MISMATCH
y ESTILO (tu palabra más usada). Todas las ops verifican el valor previo (son
idempotentes) y respetan el CANDADO (nunca tocan capítulos cerrados).

AVISO CONSTRUCT vs ESTILO: CONSTRUCT añade «de» a todo constructo común, pero
ESTILO puede indicar que tú NO usas «de» para esa forma. Si notas "churn"
(el motor añade «de» y luego ESTILO lo marca), define la política del «de»
y, o bien saca CONSTRUCT de AUTOFIX (solo reporte), o haz que consulte ESTILO.

AVISO sobre CANON --apply: el canon se arma con glosas UNÁNIMES de la fuente. Un
homógrafo que es monosémico en la fuente pero polisémico fuera (p.ej. שְׂפַת
«lenguaje» en Babel vs «orilla» junto al mar) puede sugerir revertir una glosa
correcta. Revisa las sugerencias CANON antes de aplicar en pasajes nuevos.

Rutas: robustas y relativas al repo (NO usa book_config, que tenía ruta obsoleta).

CATEGORÍAS
──────────
  MALFORM   caracteres hebreos/griegos/control/raros, dobles espacios,
            paréntesis desbalanceados, glosa larguísima, placeholder [EN:],
            inglés SIN traducir aunque no lleve [EN:] (second, land, women…)
  VACIO     morf. de contenido (SUBS/VERBO/ADJ…) con `es` vacío; prefijo con
            forma pero sin glosa; sufijo con forma pero sin glosa
  CORTO     token "cut-short": el radical quedó vacío pero hay prefijo/sufijo
            → render "sus ---", "con ---", "he ---" (punto 9 del usuario)
  LARGO     un token hebreo cuya glosa (raíz+sufijo, sin prefijos) tiene 3+
            palabras españolas. Lo normal es 1–2; 3+ es raro y casi siempre
            arrastre/corrupción («su él pies», «porción la comida de»).
            Se excluyen perífrasis de contenido («dio a luz», «peso de honra»).
            Solo reporte.
  DOBLE     palabras repetidas consecutivas en el render final del versículo;
            apilamiento de posesivos "su sus", "mi mis", etc.
  RENDER    reconstruye prefijo+raíz+sufijo como el visor (combinar_es) y marca
            el string final malformado: posesivo/clítico + posesivo
            ("nuestro tu muerta"), + preposición ("mi por si acaso", "su en
            medio"), + conjunción ("su y") o + artículo ("su un"). Señala glosa
            base corrupta. Solo reporte.
  CONCORD   artículo definido que no concuerda con la morfología (el/la/los/las);
            sufijo posesivo plural glosado en singular
  PRON      preposición+pronombre redundante ante sufijo; presentativo הִנֵּה
  POSES     posesivos apilados en raíz+sufijo ("su sus")
  MORPH_MISMATCH  la morfología es PREP pero la glosa no es preposicional
            (homógrafo mal alineado, p.ej. עם con↔pueblo)
  ENCLIT    infinitivo con pronombre objeto ANTEPUESTO ("la llorar") → debe ir
            enclítico y unido ("llorarla"); solo reporte + sugerencia
  RECORRIDO glosa idéntica al token vecino (salto del spider); glosa que parece
            nombre propio en un token que NO es NPROP
  CANON     glosa que incumple el canon unánime de un rango fuente
            (por defecto 1:1 hasta el último verso del último capítulo CERRADO)
            → CORREGIBLE automáticamente
  TRANSLIT  NPROP/GENT con glosa en minúscula, vacía, con [EN:] o con hebreo
  PENINSULAR  español de España (vosotros, sois, -áis, coche…) → CORREGIBLE
  YHWH      tetragrámaton con glosa distinta de Adonai/'Elohim/Hashem

USO
───
    # revisar un capítulo (dry-run, informe)
    python motores/scripts/revisar_es.py --book genesis --chapter 21

    # revisar un rango
    python motores/scripts/revisar_es.py --book genesis --from 19:1 --to 24:67

    # revisar libro completo
    python motores/scripts/revisar_es.py --book salmos

    # aplicar SOLO arreglos seguros (canon + peninsular) con respaldo
    python motores/scripts/revisar_es.py --book genesis --chapter 21 --apply

    # elegir categorías
    python motores/scripts/revisar_es.py --book genesis --chapter 21 --only CANON PENINSULAR
    python motores/scripts/revisar_es.py --book genesis --chapter 21 --skip VACIO

    # forzar el rango fuente del canon (si no, 1:1 → último cap. cerrado)
    python motores/scripts/revisar_es.py --book genesis --chapter 27 --source-to 26:35
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# ── Candado de capítulos terminados (nunca se modifican) ────────────────────
try:
    from candado import esta_bloqueado, capitulos_bloqueados
except Exception:  # pragma: no cover
    def esta_bloqueado(libro, capitulo):  # type: ignore
        return False
    def capitulos_bloqueados(libro):  # type: ignore
        return set()

# ── Reutilización de motores existentes (librerías) ─────────────────────────
try:
    from es_latam_neutral import to_latam_neutral
except Exception:  # pragma: no cover
    def to_latam_neutral(t):  # type: ignore
        return t

try:
    from glosas_personales_utils import tetragrammaton_es, clean_hebrew, load_registry
except Exception:  # pragma: no cover
    def tetragrammaton_es(hf, default='Hashem'):  # type: ignore
        return default

    def clean_hebrew(s):  # type: ignore
        return (s or '').strip()

    def load_registry(path=None):  # type: ignore
        return {'global': [], 'contexto': []}

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / 'data_master'
GLOSAS = ROOT / 'fuentes' / 'glosas_personales.json'

# ── Regex / vocabularios ────────────────────────────────────────────────────
NIQ = re.compile(r'[\u0591-\u05C7]')
HEB_LETTER = re.compile(r'[\u05D0-\u05EA]')
GRK_LETTER = re.compile(r'[\u0370-\u03FF\u1F00-\u1FFF]')
CTRL_CHAR = re.compile(r'[\x00-\x1F\x7F]')
WEIRD_SYM = re.compile(r'[<>&{}\\^~`]')
EN_PLACEHOLDER = re.compile(r'\[EN:')
# ── Inglés "pelado" (sin envoltura [EN:]) ────────────────────────────────────
# Palabras que son inglés y NUNCA una palabra válida en español ni una
# transliteración. Se EXCLUYEN a propósito homógrafos español↔inglés
# (has, come, comes, son, one, man, van, sea, ser, di, da, ve, he…) para no
# generar falsos positivos. Se comparan como PALABRA COMPLETA, sin distinguir
# mayúsculas. Sirve para cazar residuos del pipeline como "second", "third",
# "land", "women" que quedaron sin el marcador [EN:].
EN_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ']+")
EN_BARE = {
    # ordinales
    'first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh',
    'eighth', 'ninth', 'tenth',
    # artículos / determinantes / pronombres
    'the', 'they', 'them', 'their', 'this', 'that', 'these', 'those',
    'there', 'here', 'its', 'who', 'whom', 'whose', 'which', 'what',
    # auxiliares / verbos frecuentes (nunca español)
    'will', 'shall', 'would', 'could', 'should', 'said', 'saying',
    'have', 'had', 'was', 'were', 'been', 'being', 'does', 'did', 'done',
    'made', 'make', 'makes', 'went', 'given', 'taken', 'take', 'give',
    'came',  # 'come'/'comes' se EXCLUYEN (español: comer)
    # conjunciones / preposiciones / adverbios
    'and', 'because', 'before', 'after', 'under', 'upon', 'into', 'through',
    'against', 'between', 'among', 'toward', 'towards', 'out', 'over',
    'than', 'then', 'about', 'while', 'when', 'where', 'down', 'off',
    'away', 'back', 'again', 'also', 'even', 'just', 'only', 'still',
    # sustantivos frecuentes del pipeline
    'water', 'waters', 'woman', 'women', 'wife', 'mother', 'daughter',
    'children', 'land', 'day', 'days', 'name', 'thing', 'things',
    # términos bíblicos que los motores base suelen colar en inglés
    # (NO incluir transliteraciones legítimas: «Lud», «Sur/Shur», etc.)
    'lord', 'lords', 'god', 'gods', 'king', 'kings',
    'earth', 'heaven', 'heavens',
    # sustantivos de contenido (cuerpo/parentesco/lugar/objeto) que el spider suele
    # dejar en inglés. Se EXCLUYEN colisiones con español: «son» (ellos son),
    # «pan/mano» no aplican, «come/comes» ya excluidos arriba.
    'womb', 'belly', 'seed', 'offspring', 'nation', 'nations',
    'people', 'peoples', 'brother', 'brothers', 'sister', 'sisters',
    'father', 'servant', 'servants', 'maidservant', 'handmaid',
    'house', 'houses', 'field', 'fields', 'city', 'cities',
    'hand', 'hands', 'eye', 'eyes', 'heart', 'voice', 'word', 'words',
    'blood', 'flesh', 'sword', 'gold', 'silver', 'cattle',
    'flock', 'flocks', 'herd', 'herds', 'well', 'wells', 'stone',
    'tree', 'trees', 'bread', 'famine', 'covenant', 'birthright',
    'blessing', 'firstborn',
}

CONTENT_ROOTS = ('SUBS', 'VERBO', 'VERB', 'ADJ', 'ADV', 'NUM')
# raíces cuyo contenido NUNCA debería quedar reducido a una palabra funcional
LEXICAL_ROOTS = ('SUBS', 'VERBO', 'VERB', 'ADJ')
# palabras funcionales que, solas, NO pueden ser la glosa de un sustantivo/verbo/adjetivo
FUNCTION_ONLY = {
    'se', 'le', 'les', 'me', 'te', 'os', 'lo', 'la', 'los', 'las',
    'y', 'o', 'u', 'e', 'el', 'un', 'una', 'su', 'sus', 'mi', 'mis',
    'tu', 'tus', 'de', 'a', 'que', 'nos',
    # pronombres-sujeto: nunca son la glosa de un SUBS/VERBO/ADJ de contenido
    'yo', 'tú', 'él', 'ella', 'ellos', 'ellas', 'nosotros', 'nosotras',
    'ustedes', 'usted',
}

ES_PROCLITICS = {
    'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
    'mi', 'mis', 'tu', 'tus', 'su', 'sus',
    'nuestro', 'nuestra', 'nuestros', 'nuestras',
    'vuestro', 'vuestra', 'vuestros', 'vuestras',
    'me', 'te', 'se', 'nos', 'os', 'le', 'les', 'lo',
}
ES_TONICS = {
    'él', 'ella', 'ellos', 'ellas', 'mí', 'ti', 'sí',
    'conmigo', 'contigo', 'consigo',
    'nosotros', 'nosotras', 'ustedes', 'usted', 'vosotros', 'vosotras',
}
# pronombres SUJETO/TÓNICOS que NUNCA deben encabezar la raíz de un sustantivo:
# cuando aparecen ahí ante un sufijo pronominal son un doble espurio del mismo
# sufijo hebreo (p.ej. «él pies» + suf «su» = ambos del ו 3ms → «su él pies»).
TONIC_SUBJ_STEM = ES_TONICS | {'yo', 'tú', 'ello'}
POSSESSIVES = {
    'mi', 'mis', 'tu', 'tus', 'su', 'sus',
    'nuestro', 'nuestra', 'nuestros', 'nuestras',
    'vuestro', 'vuestra', 'vuestros', 'vuestras',
}
# Posesivos LARGOS/tónicos: en español el posesivo PRENOMINAL es la forma átona
# (mi/tu/su); estas formas largas NUNCA deben encabezar la raíz de un sustantivo.
# Cuando aparecen en la raíz Y hay sufijo pronominal, son arrastre RVR espurio
# que produce el doble visible («mi mío señor», «mi nuestro señor»). El posesivo
# correcto lo aporta el sufijo hebreo → se quitan de la raíz.
LONG_POSS = {
    'mío', 'mía', 'míos', 'mías',
    'tuyo', 'tuya', 'tuyos', 'tuyas',
    'suyo', 'suya', 'suyos', 'suyas',
    'nuestro', 'nuestra', 'nuestros', 'nuestras',
    'vuestro', 'vuestra', 'vuestros', 'vuestras',
}
# pronombre tónico → posesivo (un sustantivo con sufijo pronominal SIEMPRE lleva
# posesivo, nunca tónico: קִבְרוֹ = «su sepultura», no «sepultura él»)
_TONIC2POSS = {
    'mí': 'mi', 'ti': 'tu', 'él': 'su', 'ella': 'su', 'ellos': 'su',
    'ellas': 'su', 'sí': 'su', 'ustedes': 'su', 'usted': 'su',
    'nosotros': 'nuestro', 'nosotras': 'nuestra',
    'vosotros': 'vuestro', 'vosotras': 'vuestra',
}
ARTICLES_ES = {'el', 'la', 'los', 'las'}
VALID_SHORT_ES = {
    'y', 'a', 'o', 'no', 'él', 'yo', 'tú', 'me', 'te', 'se', 'le', 'lo', 'la',
    'de', 'en', 'ni', 'si', 'ya', 'sé', 've', 'da', 'di', 'al', 'mi', 'su',
    'un', 'es', 'ir', 'ha', 'he', 'oh', 'ay', 'sí',
}
DEMOSTRATIVOS = {
    'este', 'esta', 'estos', 'estas', 'ese', 'esa', 'esos', 'esas',
    'aquel', 'aquella', 'aquellos', 'aquellas', 'esto', 'eso', 'aquello',
}
# género/número de demostrativos y artículos (para concordancia art.+demostrativo)
DEMO_GN = {
    'este': ('m', 's'), 'ese': ('m', 's'), 'aquel': ('m', 's'),
    'esta': ('f', 's'), 'esa': ('f', 's'), 'aquella': ('f', 's'),
    'estos': ('m', 'p'), 'esos': ('m', 'p'), 'aquellos': ('m', 'p'),
    'estas': ('f', 'p'), 'esas': ('f', 'p'), 'aquellas': ('f', 'p'),
}
ART_GN = {'el': ('m', 's'), 'la': ('f', 's'), 'los': ('m', 'p'), 'las': ('f', 'p')}
GN_ART = {v: k for k, v in ART_GN.items()}
# familia de demostrativo → forma correcta por (género, número). El NÚMERO lo fija
# la morfología hebrea (autoridad); el GÉNERO, el sustantivo español al que
# acompaña. Sirve para concordar un demostrativo SUELTO con su referente vecino
# («estas años»→«estos años»). Los neutros (esto/eso/aquello) NO están: no concuerdan.
DEMO_FAM = {
    'este': 'este', 'esta': 'este', 'estos': 'este', 'estas': 'este',
    'ese': 'ese', 'esa': 'ese', 'esos': 'ese', 'esas': 'ese',
    'aquel': 'aquel', 'aquella': 'aquel', 'aquellos': 'aquel', 'aquellas': 'aquel',
}
DEMO_TABLE = {
    'este':  {('m', 's'): 'este',  ('f', 's'): 'esta',    ('m', 'p'): 'estos',    ('f', 'p'): 'estas'},
    'ese':   {('m', 's'): 'ese',   ('f', 's'): 'esa',     ('m', 'p'): 'esos',     ('f', 'p'): 'esas'},
    'aquel': {('m', 's'): 'aquel', ('f', 's'): 'aquella', ('m', 'p'): 'aquellos', ('f', 'p'): 'aquellas'},
}
# posesivo singular → plural (concordancia con el sustantivo POSEÍDO en español)
POSS_SG2PL = {'su': 'sus', 'mi': 'mis', 'tu': 'tus'}
# títulos divinos transliterados que SÍ llevan artículo en el estilo del usuario
DIVINE_ART_OK = {"'elohim", "'el", "'eloah"}
FUNC_WORDS = ES_PROCLITICS | ES_TONICS | {'y', 'o', 'de', 'a', 'que', 'no'}
# palabras cuya repetición consecutiva SIEMPRE es error (artículos, preps,
# posesivos, clíticos, conjunciones). Los dobles de contenido/nombres propios
# ("Abraham Abraham", repetición distributiva "día día") son legítimos y NO se marcan.
PREP_HEADS = {
    'a', 'de', 'con', 'en', 'sobre', 'hacia', 'para', 'por', 'hasta',
    'entre', 'desde', 'tras', 'ante', 'bajo', 'contra', 'según', 'sin',
}
# cabezas válidas para la glosa de una PREPOSICIÓN hebrea (prep. + adverbios
# locativos/relacionales frecuentes). Si la glosa de un PREP NO empieza por una
# de estas ni por una funcional, es sospechosa (homógrafo, p.ej. עם con↔pueblo).
# Un VERBO glosado EXACTAMENTE como una de estas palabras funcionales sueltas
# es casi siempre un RECORRIDO: la glosa de una ficha contigua (típicamente la
# preposición לְ «a/para/por») invadió el verbo, que quedó sin su glosa léxica.
_VERBO_RECORRIDO = PREP_HEADS | {'y', 'o', 'e', 'u', 'ni', 'que'}
PREP_ES_HEADS = PREP_HEADS | {
    'cabe', 'durante', 'mediante', 'so', 'al', 'del', 'junto', 'cerca',
    'encima', 'debajo', 'dentro', 'fuera', 'delante', 'detrás', 'detras',
    'alrededor', 'acerca', 'conforme', 'frente', 'respecto', 'través',
    'traves', 'antes', 'después', 'despues', 'arriba', 'abajo', 'adentro',
    'afuera', 'lejos', 'aparte', 'además', 'ademas', 'enfrente',
    # partículas hebreas (כ, כמו, ב/כ+inf) que se vierten como comparativas o
    # temporales: son glosas VÁLIDAS de preposición, no homógrafos
    'como', 'cuando', 'mientras', 'tal', 'así', 'asi', 'tan', 'cual',
    # partículas hebreas que se vierten como excepción/interrogación/compañía
    'excepto', 'salvo', 'menos', 'acaso', 'juntos', 'aparte',
}
DOUBLE_FUNC = FUNC_WORDS | PREP_ES_HEADS | {'un', 'una', 'unos', 'unas'}
PRON_TAIL = {
    'mí', 'ti', 'él', 'ella', 'ello', 'sí', 'nosotros', 'nosotras',
    'vosotros', 'vosotras', 'ellos', 'ellas',
}
# femeninos que NO terminan en -a (o terminan en -o): «la mano», «la tribu»
FEM_O = {'mano', 'foto', 'moto', 'libido', 'soprano', 'tribu'}
MASC_A = {
    'día', 'dia', 'mapa', 'clima', 'tema', 'problema', 'sistema', 'idioma',
    'programa', 'poema', 'poeta', 'profeta', 'planeta', 'drama', 'aroma',
    'dilema', 'enigma', 'fantasma', 'mediodía', 'tranvía', 'patriarca', 'sofá',
    # masculinos terminados en -á/-a muy frecuentes en el Tanaj
    'maná', 'mana',
    # -ma griego / cosas inequívocamente masculinas halladas en el corpus:
    'anatema',
}
# género COMÚN (el/la según el referente) o dudoso: NO se autocorrige el artículo
# (forzar un género sería tan erróneo como el original). expected_article→None.
GENERO_AMBIGUO = {
    'escriba', 'levita', 'guía', 'centinela', 'vigía', 'monarca', 'sátrapa',
    'satrapa', 'homicida', 'testigo', 'israelita', 'moabita', 'amonita',
    'edomita', 'amalecita', 'hitita', 'heteo', 'efa', 'gomer',
    'idólatra', 'idolatra', 'idumea', 'suicida', 'colega', 'compatriota',
}
A_TONICA = {
    'agua', 'alma', 'área', 'area', 'hambre', 'arma', 'águila', 'aguila',
    'hacha', 'ave', 'aula', 'haba', 'ala', 'ancla', 'acta', 'habla', 'asa',
    'hada', 'arpa', 'ascua', 'arca', 'ancha', 'aya', 'ánfora', 'anfora',
    'alba', 'asna', 'hampa', 'águeda', 'asma',
}
# adverbios/invariables terminados en -a/-o que NO son sustantivos con género:
# el heurístico «-a→f / -o→m» los clasificaría mal («afuera»→f→«la afuera»).
# Aparecen glosando sustantivos hebreos usados adverbialmente (he direccional:
# חוצה «afuera», שמה «allá»…). Ante ellos expected_article NO opina → sin autofix.
ADV_INVAR = {
    'afuera', 'fuera', 'adentro', 'dentro', 'arriba', 'abajo', 'encima',
    'debajo', 'delante', 'detrás', 'detras', 'cerca', 'lejos', 'alrededor',
    'ahora', 'nunca', 'siempre', 'jamás', 'jamas', 'todavía', 'todavia',
    'acá', 'aca', 'allá', 'alla', 'aquí', 'aqui', 'allí', 'alli', 'ahí', 'ahi',
    'así', 'asi', 'apenas', 'nada', 'contra', 'hacia', 'tras',
    # cuantificadores / determinantes / formas verbales sueltas glosando un SUBS
    # (no son sustantivos con género → sin autofix de artículo):
    'poco', 'poca', 'mucho', 'mucha', 'harto', 'harta', 'cualquiera',
    'hasta', 'había', 'habia', 'quizá', 'quiza', 'cada', 'dos', 'tres',
    'ambos', 'ambas', 'sendos', 'varios', 'varias', 'demás', 'demas',
}

CATEGORIES = ['MALFORM', 'PUNTOCOMA', 'VACIO', 'CORTO', 'LARGO', 'DOBLE', 'RENDER',
              'POSES', 'CONCORD', 'PRON', 'PREPRON', 'MORPH_MISMATCH', 'HOMOGRAF',
              'EUFONIA', 'VAV', 'KI', 'PEN', 'CONJUGA', 'TIEMPOVERBAL', 'SINTAXIS', 'CONSTRUCT',
              'MORFO', 'ENCLIT', 'GLOSAFUNC', 'CONTAGIO', 'RECORRIDO', 'CANON', 'TRANSLIT',
              'SINSTRONG', 'PENINSULAR', 'YHWH', 'ESTILO', 'REFLEX', 'REFUERZO']
# Se auto-aplican con --apply. Además de CANON/PENINSULAR/CONSTRUCT, ahora se
# corrigen las clases DETERMINISTAS de posesivos/pronombres que reaparecían
# capítulo a capítulo ("su sus hijos", "su nombres"→"sus nombres", "a él él"):
#   POSES  → EL SUFIJO HEBREO ES LA AUTORIDAD. (a) limpia sufijo redundante
#            (clear_prs) cuando la raíz ya lo representa bien; (b) quita el
#            posesivo largo/tónico espurio de la raíz (set_es); (c) cuando la raíz
#            trae un posesivo que NO concuerda con el sufijo —distinta persona
#            («su mi padre») o distinto nº de poseedor («mi»↔«nuestro»)—
#            reconstruye el posesivo correcto DESDE el sufijo y limpia (poss_rehome).
#            Solo SUBS con resto de contenido; lo dudoso → reporte.
#   CONCORD→ número del sufijo/posesivo (su→sus ante plural). Los ARTÍCULOS
#            (el/la/los/las) NO se auto-tocan (evita falsos positivos tribu/maná).
#   PRON   → quita el pronombre redundante de raíces preposicionales / idiom הנה.
#            NUNCA sobre VERBO (un verbo con sufijo lleva OBJETO legítimo).
#   PREPRON→ preposición + sufijo pronominal con el render ROTO: raíz glosada con
#            palabra funcional errónea («un mí», «y él», «su ellos») o preposición
#            SIN el pronombre («a», «para» solas). La PREPOSICIÓN la fija el
#            esqueleto hebreo de forma DETERMINISTA (אל→a, ב→en, מן→de, על→sobre,
#            אחר→tras, עד→hasta; עם/את→con vía HOMOGRAF) y el PRONOMBRE tónico lo
#            reconstruye la morfología del sufijo. ל con raíz basura → «a»+pron
#            (default; a↔para es estilo tuyo, ajustable; nunca deja «un mí»).
#   HOMOGRAF→ שם/שמה(ADV)→allí, שֵׁם(SUBS)→nombre, עם(PREP «pueblo»)→con,
#            ילד(VERBO «luz»)→«dio/dar a luz» (con el tiempo correcto).
#   VAV    → el vav CONSECUTIVO de un WAYYIQTOL es narrativo («y»), nunca conjunción
#            de PROPÓSITO/FINAL: prefijo CONJ glosado «para que»/«para»… sobre
#            wayyiqtol → «y» («para que luchaban»→«y luchaban», 25:22).
#   CONSTRUCT→ añade «de» a constructos nominales; NO sobre glosa adverbial/verbal.
#   REFLEX → verbos de postración pronominales (קדד/שחה/כרע/שחח) sin reflexivo:
#            añade el clítico que CONCUERDA con la persona hebrea («inclinó»→«se
#            inclinó», «incliné»→«me incliné»). NO toca נטה H5186 (transitivo).
# MORPH_MISMATCH/ESTILO siguen siendo solo reporte (requieren criterio léxico).
# Nombre divino en minúscula → MORPH_MISMATCH (reporte: distinguir dioses ajenos).
#   GLOSAFUNC→ lexema de contenido (SUBS/ADJ/VERBO) glosado como palabra FUNCIONAL
#            pura (y/de/el/que/su…) = corrupción del build. Se restaura la glosa
#            preferida POR-FORMA de tu estadística SOLO si es NOMINAL, palabra de
#            contenido limpia, n≥6, pct≥50 (autofix); el resto → reporte con
#            candidato. Cierra el hueco: ESTILO se abstenía en lexemas ambiguos y
#            la corrupción pasaba en silencio.
AUTOFIX = {'CANON', 'PENINSULAR', 'CONSTRUCT', 'POSES', 'CONCORD', 'PRON', 'PREPRON',
           'HOMOGRAF', 'EUFONIA', 'CONJUGA', 'PUNTOCOMA', 'TIEMPOVERBAL', 'REFLEX',
           'TRANSLIT', 'VAV', 'KI', 'PEN', 'GLOSAFUNC', 'CONTAGIO', 'REFUERZO'}

try:
    import estilo_usuario
except Exception:  # pragma: no cover
    estilo_usuario = None

try:
    import inferir_strongs
except Exception:  # pragma: no cover
    inferir_strongs = None


# ── Helpers ─────────────────────────────────────────────────────────────────
def consk(s: str) -> str:
    return ''.join(c for c in NIQ.sub('', s or '') if 0x05D0 <= ord(c) <= 0x05EA)


def parse_ref(s: str) -> tuple[int, int]:
    if ':' not in str(s):
        return (int(s), 1)
    ch, vs = str(s).split(':', 1)
    return (int(ch), int(vs))


def last_verse_of_chapter(d, chapter: int) -> int:
    last = 0
    for v in d.get('verses') or []:
        if int(v.get('chapter') or 0) == int(chapter):
            last = max(last, int(v.get('verse') or 0))
    return last


def default_canon_source_to(book, d, locked=None) -> str:
    """Último verso del último capítulo CERRADO: lo ya aprendido, no un tope fijo."""
    caps = set(locked) if locked is not None else capitulos_bloqueados(book)
    if not caps:
        return '1:0'
    ch = max(int(x) for x in caps)
    vs = last_verse_of_chapter(d, ch)
    return f'{ch}:{vs}' if vs > 0 else f'{ch}:999'


def in_range(ch: int, vs: int, lo: tuple[int, int], hi: tuple[int, int]) -> bool:
    return lo <= (ch, vs) <= hi


def morph_root(m: str) -> str:
    # Corta primero en '+' (morfologías compuestas tipo «PREP+PRS.P1.SG»): la raíz
    # POS es el primer átomo, igual que morph_pos_root del motor hebreo. Sin esto,
    # un stem compuesto devolvía «PREP+PRS» y no casaba con ningún check (== 'PREP').
    return (m or '').split('+')[0].split('.')[0]


def is_content(m: str) -> bool:
    return morph_root(m) in CONTENT_ROOTS


def is_nprop_gent(m: str) -> bool:
    return m == 'NPROP' or (m or '').startswith('NPROP') or (m or '').startswith('GENT')


def is_tetra(hw: dict) -> bool:
    return consk(hw.get('he_form') or '') in ('יהוה', 'יהויה')


def prefix_es_list(hw: dict) -> list[str]:
    pl = hw.get('prefix_es') or []
    return [str(x or '') for x in pl] if isinstance(pl, list) else []


def prs_es(hw: dict) -> str:
    prs = hw.get('prs_suffix') or {}
    return str(prs.get('es') or '') if isinstance(prs, dict) else ''


def prs_he(hw: dict) -> str:
    prs = hw.get('prs_suffix') or {}
    return str(prs.get('he_form') or '') if isinstance(prs, dict) else ''


def prs_morph(hw: dict) -> str:
    prs = hw.get('prs_suffix') or {}
    return str(prs.get('he_morph') or '') if isinstance(prs, dict) else ''


def is_pron_suffix(prs_m: str) -> bool:
    """True si el sufijo es PRONOMINAL (PRS.*): posesivo (mi/tu/su…) u objeto
    (lo/le…). False para sufijos NO pronominales que el motor hebreo distingue —
    he/nun paragógico y he locativo/direccional (SUF, SUF.PARAG.HE/NUN, «-áh»
    hacia) y PART—: esos NO deben tratarse como posesivo ni como objeto. Sin
    etiqueta o etiqueta desconocida devuelve True (no bloquea; conserva la lógica
    histórica de tokens sin morfología de sufijo)."""
    u = (prs_m or '').upper()
    if not u:
        return True
    if u.startswith('PRS'):
        return True
    return not any(t in u for t in ('SUF', 'PARAG', 'PART'))


def canon_key(hw: dict) -> tuple:
    """Clave de canonicidad basada SOLO en el lado hebreo (Strong + morfología +
    forma consonántica). NO incluye el español objetivo (prefix_es / prs_es): si
    lo incluyera, una glosa rota o incompleta no emparejaría con el canon y el
    error pasaría inadvertido (falso negativo). Debe usarse idéntica en
    build_canon() y en el chequeo CANON de run()."""
    return (
        (hw.get('strongs') or '').strip(),
        hw.get('he_morph') or '',
        tuple(hw.get('prefix_morphs') or []),
        prs_morph(hw),
        consk(hw.get('he_form') or ''),
    )


def combine_es_suffix(stem: str, suf: str, stem_morph: str = '') -> str:
    """Delega en combinar_es(): una ÚNICA fuente de verdad del render (evita que
    dos espejos del JS se desincronicen; antes esta réplica no tenía la lógica
    enclítica y devolvía "la llorar" en vez de "llorarla")."""
    return combinar_es(stem, suf, stem_morph)


def render_token(hw: dict) -> str:
    pref = ' '.join(p for p in prefix_es_list(hw) if p)
    core = combinar_es((hw.get('es') or ''), prs_es(hw), hw.get('he_morph') or '')
    return (f'{pref} {core}' if pref else core).strip()


# sustantivos SINGULARES terminados en -s (invariables o no): la heurística
# «termina en -s ⇒ plural» los clasificaría mal → artículo/posesivo erróneo.
SINGULAR_IN_S = {
    'dios', 'país', 'pais', 'mes', 'interés', 'interes', 'análisis', 'analisis',
    'atlas', 'virus', 'oasis', 'iris', 'crisis', 'tesis', 'dosis', 'síntesis',
    'sintesis', 'énfasis', 'enfasis', 'gas', 'arnés', 'arnes', 'ciprés', 'cipres',
    'mies', 'res', 'tos', 'vals', 'lunes', 'martes', 'miércoles', 'miercoles',
    'jueves', 'viernes',
}


def es_number(w: str) -> str:
    if w in SINGULAR_IN_S:
        return 's'
    return 'p' if (len(w) > 2 and w.endswith('s')) else 's'


def es_gender(w: str):
    if w in FEM_O:
        return 'f'
    if w in MASC_A:
        return 'm'
    if w in A_TONICA:
        return 'f'
    base = w[:-1] if (w.endswith('s') and len(w) > 2) else w
    if base in MASC_A:                 # plurales masc en -a: «días»→«día» (m)
        return 'm'
    if base in FEM_O:
        return 'f'
    if base in A_TONICA:               # plural a-tónica: «aguas» (f)
        return 'f'
    if base.endswith('a'):
        return 'f'
    if base.endswith('o'):
        return 'm'
    return None


_ART_WORD_RE = re.compile(r"[a-záéíóúüñ][a-záéíóúüñ'\-]*$")


def _articulable(w: str) -> bool:
    """True solo si `w` es una palabra española a la que tiene sentido asignar
    artículo definido con género/número (un sustantivo común). False para
    invariables/adverbios, género común/ambiguo, glosas rotas ([EN:], corchetes),
    gerundios (verbo) y cualquier cosa no puramente alfabética. Blinda el
    autofix de artículo contra falsos positivos («la afuera», «los eufrates»)."""
    if not w:
        return False
    w = w.lower()
    base = w[:-1] if (w.endswith('s') and len(w) > 2) else w   # singular aprox.
    if (w in FUNC_WORDS or w in DEMOSTRATIVOS or w in ADV_INVAR
            or w in GENERO_AMBIGUO or base in GENERO_AMBIGUO):
        return False
    if w.endswith(('ando', 'endo', 'iendo')):        # gerundio → verbo
        return False
    return bool(_ART_WORD_RE.match(w))               # solo letras/acentos/guion


def expected_article(noun: str):
    """Artículo definido esperado según género/número del sustantivo ESPAÑOL.
    Devuelve None si el sustantivo es ambiguo (evita falsos positivos)."""
    if not noun:
        return None
    w = noun.strip().split()[0].lower()
    if not _articulable(w):
        return None
    g = es_gender(w)
    if g is None:
        return None
    n = es_number(w)
    if w in A_TONICA and n == 's':
        return 'el'                     # el agua, el alma (a- tónica)
    if g == 'f':
        return 'las' if n == 'p' else 'la'
    return 'los' if n == 'p' else 'el'


_VERB_FINITO_TAGS = ('WAYYIQT', 'QATAL', 'IMPF', 'WEQATAL', 'JUSS', 'COHO', 'IMPV')


def _es_verbo_finito(mm):
    return morph_root(mm) == 'VERBO' and any(t in (mm or '') for t in _VERB_FINITO_TAGS)


def demo_referent_gender(flat, idx):
    """Género ESPAÑOL (m/f) del sustantivo referente de un demostrativo, eligiendo
    la DIRECCIÓN por adyacencia:
      1) ATRIBUTIVO — si el token de contenido inmediatamente ANTERIOR es un SUBS/
         ADJ, el demostrativo va TRAS su sustantivo («la tierra esta», «generación
         esta») → ese es el referente. (Es el orden hebreo del demostrativo
         atributivo: sustantivo + הַזֶּה/הַזֹּאת/הָאֵלֶּה.)
      2) PREDICATIVO — si no (el demostrativo ABRE la cláusula: «estas [son] años/
         hijos»), primer SUBS/ADJ hacia ADELANTE, saltando enlazadores (cópula
         «son», pronombre הֵם, artículo/relativo) y cortando en VERBO FINITO.
    Usa el género ESPAÑOL del referente (NO el hebreo: דּוֹר masc → «generación» fem
    → «esta»; por eso el género lo fija la glosa, no la morfología). Devuelve None si
    no hay certeza (referente propio, número/adverbio, género ambiguo)."""
    def gen_de(w):
        mm = w.get('he_morph') or ''
        if morph_root(mm) not in ('SUBS', 'ADJ') or is_nprop_gent(mm):
            return None
        es0 = (w.get('es') or '').strip()
        if not es0:
            return None
        words = es0.lower().split()
        k = 0                            # salta artículo/posesivo inicial → cabeza nominal
        while k < len(words) and (words[k] in ARTICLES_ES
                                  or words[k] in POSSESSIVES
                                  or words[k] in LONG_POSS):
            k += 1
        if k >= len(words) or not _articulable(words[k]):
            return None
        return es_gender(words[k])
    for j in range(idx - 1, -1, -1):     # 1) vecino de contenido inmediato ANTERIOR
        w = flat[j][2]
        if not (w.get('es') or '').strip():
            continue
        mm = w.get('he_morph') or ''
        if morph_root(mm) in ('SUBS', 'ADJ') and not is_nprop_gent(mm):
            return gen_de(w)             # atributivo: ese sustantivo manda (género o None)
        break                            # vecino inmediato no-nominal → es predicativo
    for j in range(idx + 1, len(flat)):  # 2) predicativo: primer SUBS/ADJ hacia adelante
        w = flat[j][2]
        mm = w.get('he_morph') or ''
        if _es_verbo_finito(mm):
            break
        if morph_root(mm) in ('SUBS', 'ADJ'):
            return gen_de(w)
    return None


def looks_proper(es: str) -> bool:
    e = (es or '').strip()
    if not e:
        return False
    if e[0] == "'" and len(e) > 1 and e[1].isupper():
        return True
    return e[0].isupper()


def poss_person(w: str):
    w = (w or '').lower()
    if w in ('mi', 'mis', 'nuestro', 'nuestra', 'nuestros', 'nuestras'):
        return 1
    if w in ('tu', 'tus', 'vuestro', 'vuestra', 'vuestros', 'vuestras'):
        return 2
    if w in ('su', 'sus'):
        return 3
    return None


def suffix_person(prs_m: str):
    m = (prs_m or '').upper()
    if 'P1' in m:
        return 1
    if 'P2' in m:
        return 2
    if 'P3' in m:
        return 3
    return None


def poss_owner_number(w: str):
    """Número del POSEEDOR que codifica un posesivo español átono/tónico.
    mi/mis/tu/tus/mío/tuyo… → poseedor SINGULAR ('sg'); nuestro/vuestro… →
    poseedor PLURAL ('pl'). su/sus NO distinguen número de poseedor en español
    (3ª persona) → None (ambiguo)."""
    w = (w or '').lower()
    if w in ('mi', 'mis', 'tu', 'tus', 'mío', 'mía', 'míos', 'mías',
             'tuyo', 'tuya', 'tuyos', 'tuyas'):
        return 'sg'
    if w in ('nuestro', 'nuestra', 'nuestros', 'nuestras',
             'vuestro', 'vuestra', 'vuestros', 'vuestras'):
        return 'pl'
    return None                       # su/sus → ambiguo (3ª persona)


def suffix_owner_number(prs_m: str):
    """Número del poseedor según la morfología del sufijo hebreo (PRS…SG/PL/DU)."""
    m = (prs_m or '').upper()
    if '.PL' in m or '.DU' in m:
        return 'pl'
    if '.SG' in m:
        return 'sg'
    return None


def spanish_poss(person, owner_num, gender, noun_num) -> str:
    """Posesivo español CORRECTO dado el poseedor (persona+número que aporta el
    SUFIJO hebreo, autoridad) concordando con el sustantivo poseído (género/nº).
    Latinoamericano: 2ª plural = ustedes → «su/sus» (no «vuestro»)."""
    plural_noun = (noun_num == 'p')
    if person == 1 and owner_num == 'sg':
        return 'mis' if plural_noun else 'mi'
    if person == 1 and owner_num == 'pl':
        base = 'nuestra' if gender == 'f' else 'nuestro'
        return base + ('s' if plural_noun else '')
    if person == 2 and owner_num == 'sg':
        return 'tus' if plural_noun else 'tu'
    if person == 2 and owner_num == 'pl':
        return 'sus' if plural_noun else 'su'      # ustedes (LatAm)
    return 'sus' if plural_noun else 'su'           # 3ª persona


def hinneh_idiom(prs_m: str):
    m = (prs_m or '').upper()
    p = suffix_person(m)
    pl = '.PL' in m
    if p == 1:
        return 'henos aquí' if pl else 'heme aquí'
    if p == 2:
        return 'heos aquí' if pl else 'hete aquí'
    if p == 3:
        fem = 'F.' in m
        if pl:
            return 'helas aquí' if fem else 'helos aquí'
        return 'hela aquí' if fem else 'helo aquí'
    return None


# ── Canon (glosas unánimes del rango fuente) ────────────────────────────────
def es_norm(es: str) -> str:
    """Normaliza una glosa para comparar SENTIDO (ignora número gramatical):
    'lugares'→'lugar', 'montes'→'monte'. Así 'lugar' y 'lugares' NO cuentan como
    dos sentidos distintos, pero 'lenguaje' y 'orilla' sí."""
    out = []
    for w in (es or '').strip().lower().split():
        if len(w) > 3 and w.endswith('es'):
            w = w[:-2]
        elif len(w) > 3 and w.endswith('s'):
            w = w[:-1]
        out.append(w)
    return ' '.join(out)


def build_canon(d, lo, hi, min_n):
    """Canon = glosa UNÁNIME en el rango fuente, EXCLUYENDO claves polisémicas.

    Guard de polisemia (clave para la autonomía de --apply): si una misma clave
    canónica produce ≥2 sentidos distintos en TODO el libro (p.ej. שְׂפַת
    'lenguaje' en Babel vs 'orilla' junto al mar; עם 'con' vs 'junto con el'),
    se EXCLUYE del canon → nunca se auto-corrige por sentido. Los cambios de solo
    número (lugar/lugares) no cuentan como polisemia gracias a es_norm()."""
    seen = defaultdict(Counter)
    glob = defaultdict(set)     # sentidos (normalizados) por clave, en TODO el libro
    for v in d['verses']:
        for p in v.get('pairs') or []:
            for hw in p.get('he_words') or []:
                m = hw.get('he_morph') or ''
                if is_nprop_gent(m) or is_tetra(hw):
                    continue
                st = (hw.get('strongs') or '').strip()
                es = (hw.get('es') or '').strip()
                if not st or not es:
                    continue
                k = canon_key(hw)
                glob[k].add(es_norm(es))
                if in_range(v['chapter'], v['verse'], lo, hi):
                    seen[k][es] += 1
    ambiguous = {k for k, s in glob.items() if len(s) >= 2}
    return {k: next(iter(c)) for k, c in seen.items()
            if sum(c.values()) >= min_n and len(c) == 1 and k not in ambiguous}


def _norm_strong(st: str) -> str:
    """Normaliza un código Strong: mayúscula, prefijo H, sin ceros a la izquierda.
    «H03068»/«3068»→«H3068». Más claro y seguro que el idiom `A and B or C`."""
    s = re.sub(r'\s+', '', (st or '').upper())
    if not s:
        return s
    if s[0] != 'H':
        s = 'H' + s
    body = s[1:].lstrip('0') or '0'
    return 'H' + body


def load_protected(slug):
    glob_prot, ctx_prot = set(), set()
    try:
        reg = load_registry(GLOSAS) if GLOSAS.exists() else {'global': [], 'contexto': []}
    except Exception:
        reg = {'global': [], 'contexto': []}
    for r in reg.get('global') or []:
        st = ((r.get('match') or {}).get('strongs') or '').strip()
        if st:
            glob_prot.add(_norm_strong(st))
            glob_prot.add(st)
    for r in reg.get('contexto') or []:
        m = r.get('match') or {}
        if m.get('book') == slug and m.get('role') == 'stem':
            ctx_prot.add((m.get('chapter'), m.get('verse'), m.get('pairIdx'), m.get('hwIdx')))
    return glob_prot, ctx_prot


# ── Finding ─────────────────────────────────────────────────────────────────
class F:
    __slots__ = ('cat', 'ch', 'vs', 'pi', 'wi', 'he', 'morph', 'detail',
                 'suggest', 'field', 'protected')

    def __init__(self, cat, ch, vs, pi, wi, he, morph, detail,
                 suggest=None, field=None, protected=False):
        self.cat = cat; self.ch = ch; self.vs = vs; self.pi = pi; self.wi = wi
        self.he = he; self.morph = morph; self.detail = detail
        self.suggest = suggest; self.field = field; self.protected = protected


def finding_to_dict(f) -> dict:
    """Serializa un Finding a dict JSON. `suggest` (tupla o str) se vuelca tal
    cual (json lo emite como lista/str). `autofix` indica si la categoría se
    auto-aplica con --apply, para poder filtrar en dashboards/diffs."""
    return {
        'cat': f.cat, 'autofix': f.cat in AUTOFIX,
        'ch': f.ch, 'vs': f.vs, 'pi': f.pi, 'wi': f.wi,
        'he': f.he, 'morph': f.morph,
        'detail': f.detail, 'field': f.field,
        'protected': bool(f.protected), 'suggest': f.suggest,
    }


# ── Chequeos por token ──────────────────────────────────────────────────────
_OBJ_CLITICS = {'lo', 'la', 'los', 'las', 'le', 'les', 'me', 'te', 'se', 'nos', 'os'}
_INF_END_RE = re.compile(r'(ar|er|ir)$')
_ENCLITIC_TAIL_RE = re.compile(r'r(lo|la|los|las|le|les|me|te|se|nos|os)$')
_VERB_MORPH_RE = re.compile(r'VERB|INF|IMP|PTC|JUSS|COHOR|WAYY|QATAL|YIQT|SEQ')
_ACC_RE = re.compile(r'[áéíóúÁÉÍÓÚ]')
_CONJ_ES = {'y', 'o', 'u', 'e', 'que', 'ni', 'pero', 'sino', 'mas'}
_INDEF_ART = {'un', 'una', 'unos', 'unas'}
# numerales cardinales ES: en constructo el número precede sin «de»
_NUMERALS_ES = {
    'uno', 'una', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho',
    'nueve', 'diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis',
    'diecisiete', 'dieciocho', 'diecinueve', 'veinte', 'treinta', 'cuarenta',
    'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa', 'cien', 'ciento',
    'cientos', 'mil', 'ambos', 'ambas', 'doscientos', 'trescientos',
    'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos',
    'novecientos',
}
_DEMOS_ES = {
    'este', 'esta', 'esto', 'estos', 'estas', 'ese', 'esa', 'eso', 'esos',
    'esas', 'aquel', 'aquella', 'aquello', 'aquellos', 'aquellas',
}
# adverbios que NO reciben «de» en constructo: si un token SUBS/ADJ .C está
# glosado con uno de estos, la glosa base está mal (homógrafo/recorrido) →
# CONSTRUCT no debe añadir «de» encima («todavía de», «allí de»). Gén 29:7.
_ADV_NO_DE = {
    'todavía', 'todavia', 'aún', 'aun', 'allí', 'alli', 'allá', 'alla', 'aquí',
    'aqui', 'así', 'asi', 'ya', 'muy', 'más', 'mas', 'menos', 'siempre',
    'nunca', 'jamás', 'jamas', 'entonces', 'ahora', 'hoy', 'ayer', 'luego',
    'pronto', 'tarde', 'temprano', 'bien', 'mal', 'casi', 'apenas', 'sólo',
    'solo', 'también', 'tambien', 'tampoco', 'quizá', 'quiza', 'acaso',
}
# terminaciones verbales FINITAS inequívocas (ningún sustantivo común español
# termina así): si la glosa de un constructo termina en una de estas, es un verbo
# mal glosado y CONSTRUCT NO debe añadir «de» («parecían de» Gén 28:8). Se evita
# «-ía/-ían» sueltas por colisión con sustantivos (día, guardián, alegría…).
# SOLO terminaciones finitas INEQUÍVOCAS. Se EXCLUYEN los condicionales
# -aría/-ería/-iría porque colisionan con sustantivos en -ería (pastelería,
# panadería, carnicería…) y provocarían falsos positivos. «ían» (í acentuada) =
# imperfecto 3pl (parecían/tenían); no colisiona con «día/guardián» (á).
_VERBISH_RE = re.compile(
    r'(aban|ábamos|ábais|aron|ieron|aste|asteis|iste|isteis|áis|éis|ían)$'
)
# sustantivos/adjetivos que TERMINAN como una conjugación pero NO son verbos
# (colisionan con «-iste» de _VERBISH_RE): evita falsos positivos al detectar
# «SUBS glosado como verbo». No incluye adverbios en «-rás» (atrás/detrás): ese
# check no usa el futuro precisamente por esa colisión.
_NO_ES_VERBO = {'triste', 'chiste', 'alpiste', 'batiste', 'ariete', 'billete'}
# clíticos átonos que un verbo puede llevar ANTEPUESTOS y que hay que saltar para
# hallar el núcleo verbal («se aproximó», «me dijo», «nos habló»). No incluye
# lo/la/los/las: esos ya se saltan como ARTICLES_ES en el mismo bucle.
_LEAD_CLITICS = {'se', 'me', 'te', 'nos', 'os', 'le', 'les'}
# homógrafos funcionales que el spider suele glosar mal (esqueleto, morph_root)
# → (lectura esperada, nota). Report-only en MORPH_MISMATCH.
_HOMOGRAFOS_FUNC = {
    ('שם', 'ADV'): ('allí', 'שָׁם adverbio de lugar «allí» (no el verbo שׂם «poner»)'),
    ('שמה', 'ADV'): ('allá', 'שָׁמָּה adverbio direccional «allá/allí» (no el verbo שׂם «poner»)'),
    ('כן', 'ADV'): ('así', 'כֵּן adverbio «así» (no «hijo/preparar»)'),
    ('לו', 'CONJ'): ('si tan solo', 'לוּ partícula desiderativa «si tan solo / ojalá»'),
    ('לו', 'PART'): ('si tan solo', 'לוּ partícula desiderativa «si tan solo / ojalá»'),
}

# Glosas del verbo שׂם/שׂים «poner» (H7760/H7761) usadas para DETECTAR el mistag
# donde el adverbio שָׁם/שָׁמָּה (H8033, «allí») o el sustantivo שֵׁם (H8034,
# «nombre») quedaron glosados como si fueran ese verbo.
_PUT_GLOSSES = {
    'puso', 'poner', 'pondrá', 'pondra', 'pon', 'ponga', 'pongan', 'pongo',
    'puse', 'puesto', 'pondré', 'pondre', 'pondrán', 'pondran', 'pusieron',
    'pondrás', 'pondras', 'pondremos', 'pondría', 'pondria', 'ponen', 'pone',
}
# plegado de letras finales hebreas → forma regular (para unificar esqueletos)
_FINALES = str.maketrans('ךםןףץ', 'כמנפצ')

# Formas verbales españolas INEXISTENTES que el pipeline dejó mal conjugadas.
# Determinista (nunca son palabras válidas) → autofix acotado a VERBO.
# Extensible: añade aquí pares forma_mala→forma_buena verificados.
_CONJUGA_FIX = {
    'salan': 'salen',   # יצא participio/pl «salan» (no existe) → «salen»
}

# ── Lexemas de estado constructo mal glosados por el spider ─────────────────
# Sustantivos/participios en estado constructo (con sufijo pronominal) que la
# extracción automática dejó glosados como palabra funcional suelta ("y", "un",
# "de", "por si acaso"…) o con la persona equivocada. Cuando RENDER marca uno de
# estos tokens y su esqueleto consonántico CONTIENE una de estas raíces, el motor
# adjunta la glosa correcta como SUGERENCIA (nunca autofija: la palabra de
# contenido es decisión editorial). Se realimenta desde caps. 23–24.
_LEXEMA_SUGERENCIAS = {
    'קבר': 'sepultura / sepulturas',
    'תוכ': 'en medio de',
    'קרב': 'en medio de / interior de',
    'פנ': 'delante de / faz de (לפני = delante de)',
    'מת': 'difunto / difunta (participio de מות)',
    'יד': 'mano / manos',
    'חסד': 'bondad / misericordia',
    'אפ': 'nariz / rostro',
    'פי': 'boca',
    'שנא': 'enemigos (participio de שנא, "los que odian")',
    'אחת': 'hermana',
    'אחות': 'hermana',
    'שבע': 'juramento (שבועה)',
    'קרא': 'encuentro (לקראת = al encuentro de)',
    'משקל': 'peso',
    'זקנ': 'vejez / ancianidad',
    'מנק': 'nodriza',
    'בית': 'casa',
    'ימי': 'días',
    'עינ': 'ojo / ojos',
    'בינ': 'entre',
    'אשת': 'esposa / mujer de',
    'אכל': 'alimento / comida',
    'ראש': 'cabeza',
    'רגל': 'pie / pies',
    'קול': 'voz',
}


# letras de prefijo (ב ה ו כ ל מ ש) y de sufijo pronominal (ה ו י ך ם כ ן נ)
_HE_PREF = 'בהוכלמש'
_HE_SUF = 'הוינךםכ'


def _sugerir_lexema(he_form):
    """Devuelve la glosa sugerida si el esqueleto consonántico del token coincide
    con una raíz conocida de _LEXEMA_SUGERENCIAS; si no, None.

    Para raíces de 2 letras (פי, יד, אפ) NO basta `in ck`: aparecerían como
    subcadena de palabras no relacionadas (p.ej. אפרים 'Efraím' contiene אפ, y
    hay riesgo con verbos). Se exige que la raíz sea el NÚCLEO del esqueleto:
    prefijos opcionales + raíz + solo letras de sufijo pronominal."""
    ck = consk(he_form or '')
    if not ck:
        return None
    for raiz, glosa in _LEXEMA_SUGERENCIAS.items():
        if len(raiz) <= 2:
            if re.match(f'^[{_HE_PREF}]{{0,2}}{raiz}[{_HE_SUF}]*$', ck):
                return glosa
        elif raiz in ck:
            return glosa
    return None


def combinar_es(stem_es: str, suf_es: str, stem_morph: str = '') -> str:
    """ESPEJO EXACTO de combineEsWithSuffix() del visor (visor/index.html).
    Reconstruye la glosa española que realmente se muestra al unir la raíz con
    el sufijo pronominal. Mantener sincronizado con el JS: es la ÚNICA fuente de
    verdad del render, sobre la que trabaja check_render."""
    if not suf_es:
        return stem_es or ''
    if not stem_es:
        return suf_es
    s = suf_es.lower().strip()
    st = stem_es.lower().strip()
    if st == s:
        return stem_es
    toks = st.split()
    if s in toks:
        return stem_es
    if ' ' in s and s in st:
        return stem_es
    if s in _OBJ_CLITICS:
        last = toks[-1] if toks else ''
        if len(last) > len(s) and last.endswith(s):
            host = last[:len(last) - len(s)]
            if (_ENCLITIC_TAIL_RE.search(last) or host.endswith('ndo')
                    or (_VERB_MORPH_RE.search(stem_morph or '') and _ACC_RE.search(host))):
                return stem_es
        if (len(toks) == 1 and st.endswith('r')
                and ('INF' in (stem_morph or '') or _INF_END_RE.search(st))):
            return f'{stem_es}{s}'
    if s in ES_PROCLITICS:
        return f'{suf_es} {stem_es}'
    if s in ES_TONICS:
        return f'{stem_es} {suf_es}'
    if s.startswith('a '):
        return f'{stem_es} {suf_es}'
    return f'{stem_es} {suf_es}'


def check_render(hw):
    """Detector AUTORITATIVO del render final malformado (una sola fuente).
    Reconstruye prefijo+raíz+sufijo tal como lo muestra el visor y marca los
    strings basura que el usuario ve: posesivo/clítico antepuesto a otro
    posesivo, a una preposición, a una conjunción o a un artículo. Estos casos
    provienen de glosas base corruptas (posesivo incrustado con persona errónea,
    o raíz glosada como palabra funcional suelta). Solo REPORTE + sugerencia:
    la corrección requiere criterio léxico (la palabra de contenido correcta)."""
    suf = hw.get('prs_suffix') or {}
    suf_es = (suf.get('es') or '').strip()
    if not suf_es:
        return None
    stem = (hw.get('es') or '').strip()
    render = combinar_es(stem, suf_es, hw.get('he_morph') or '')
    toks = render.lower().split()
    if len(toks) < 2:
        return None
    a, b = toks[0], toks[1]
    sug = _sugerir_lexema(hw.get('he_form'))
    clit = ES_PROCLITICS  # incluye clíticos objeto + posesivos
    if a in clit and b in POSSESSIVES:
        return (f'render «{render}»: posesivo/clítico + posesivo (glosa base ya '
                f'trae posesivo; debe venir solo del sufijo)', sug)
    if a in clit and b in PREP_HEADS:
        return (f'render «{render}»: clítico/posesivo + preposición '
                f'(raíz glosada como palabra suelta errónea)', sug)
    if a in clit and b in _CONJ_ES:
        return (f'render «{render}»: clítico/posesivo + conjunción '
                f'(raíz glosada como «{b}»; falta la palabra de contenido)', sug)
    if a in POSSESSIVES and (b in ARTICLES_ES or b in _INDEF_ART):
        return (f'render «{render}»: posesivo + artículo (glosa base incoherente)', sug)
    # sufijo OBJETO sobre SUSTANTIVO: en un nombre el sufijo hebreo es SIEMPRE
    # posesivo (mi/tu/su), nunca objeto. (No se incluyen participios: los
    # participios VERBALES sí toman objeto legítimo, p.ej. מֹצְאִי "el que ME halle".)
    m = hw.get('he_morph') or ''
    if suf_es.lower() in _OBJ_CLITICS and 'SUBS' in m:
        return (f'render «{render}»: sufijo objeto «{suf_es}» sobre sustantivo; '
                f'el sufijo hebreo es POSESIVO (→ mi/tu/su)', sug)
    # sufijo TÓNICO (él/mí/ti/nosotros…) sobre SUSTANTIVO: también es error, el
    # sufijo pronominal de un nombre es posesivo (קִבְרוֹ «su sepultura», no
    # «sepultura él»).
    if suf_es.lower() in ES_TONICS and 'SUBS' in m:
        poss = _TONIC2POSS.get(suf_es.lower())
        return (f'render «{render}»: sufijo tónico «{suf_es}» sobre sustantivo; '
                f'el sufijo hebreo es POSESIVO (→ {poss or "su/mi/tu"})',
                poss or sug)
    return None


def check_enclit(hw):
    """Verbo NO-FINITO en español (INFINITIVO o IMPERATIVO) cuya glosa trae el
    pronombre objeto ANTEPUESTO como proclítico ("la llorar", "me alimenta"): en
    español el clítico va ENCLÍTICO y unido al verbo → "llorarla", "aliméntame".
    Solo se dispara con morfología de INFINITIVO (INF) o IMPERATIVO (IMPV) y
    `es`="<clítico> <verbo>", para no confundir artículos ("la mujer") con clíticos.
    Solo reporte + sugerencia:
      · INFINITIVO: la unión es mecánica («llorar»+«la»→«llorarla»), se sugiere.
      · IMPERATIVO: la unión desplaza el acento («alimenta»+«me»→«aliméntame»);
        requiere criterio ortográfico → se reporta la forma aproximada (sin
        auto-fix). El clítico «se» se deja a REFLEX (verbos pronominales).
    El render normal (stem + sufijo PRS) ya se resuelve enclítico en el visor."""
    m = hw.get('he_morph') or ''
    es = (hw.get('es') or '').strip()
    toks = es.lower().split()
    if not (len(toks) == 2 and toks[0] in _OBJ_CLITICS):
        return None
    orig = es.split()
    if 'INF' in m and _INF_END_RE.search(toks[1]):
        return (f'infinitivo con clítico antepuesto «{es}» → enclítico',
                f'{orig[1]}{toks[0]}')
    if 'IMPV' in m and toks[0] != 'se' and _INF_END_RE.search(toks[1]) is None:
        return (f'imperativo con clítico objeto antepuesto «{es}» → enclítico '
                f'(p.ej. «{orig[1]}{toks[0]}», revisar acentuación)', None)
    return None


def check_malform(hw):
    es = hw.get('es')
    if es is None:
        return None
    if not isinstance(es, str):
        return f'tipo no-string ({type(es).__name__})'
    if HEB_LETTER.search(es):
        return 'contiene hebreo'
    if GRK_LETTER.search(es):
        return 'contiene griego'
    if EN_PLACEHOLDER.search(es):
        return 'placeholder [EN:]'
    en = [w for w in EN_WORD_RE.findall(es) if w.lower().strip("'") in EN_BARE]
    if en:
        return f'inglés sin traducir: {", ".join(sorted(set(en)))}'
    if CTRL_CHAR.search(es):
        return 'carácter de control'
    if WEIRD_SYM.search(es):
        return 'símbolo raro (<>&{}\\^~`)'
    if '  ' in es:
        return 'doble espacio'
    if es and es != es.strip():
        return 'espacios al borde'
    if len(es) > 60:
        return f'glosa larguísima ({len(es)})'
    if es.count('(') != es.count(')'):
        return 'paréntesis desbalanceados'
    return None


# cópulas / auxiliares: si aparecen en la RAÍZ es casi siempre arrastre de una
# cláusula RVR («es de longitud», «ella es»), no el lexema de la palabra hebrea.
_COPULAS = {
    'es', 'son', 'era', 'eran', 'fue', 'fueron', 'ser', 'soy', 'eres', 'somos',
    'sois', 'está', 'estan', 'están', 'estaba', 'estaban', 'estoy', 'estás',
    'había', 'habia', 'han', 'ha', 'he', 'has', 'hay', 'sea', 'sean', 'será',
    'serán', 'seran', 'fui', 'fuiste', 'siendo',
}
# función colgando al final de la raíz → cláusula truncada («la comida de», «a»).
_DANGLING_END = {'de', 'a', 'en', 'y', 'o', 'que', 'el', 'la', 'los', 'las',
                 'por', 'con', 'para', 'del', 'al', 'un', 'una', 'e', 'u'}
# conectores válidos de una perífrasis de contenido de 3 palabras («dio a luz»,
# «peso de honra», «dar de beber»): NO se marca en ese caso.
_CONECTOR_PERIFRASIS = {'a', 'de', 'por', 'como', 'con'}
# perífrasis FIJAS de 3 palabras ya usadas en capítulos cerrados: no se marcan
# aunque lleven artículo interno («pasar la noche») o «de» final («un poco de»).
_PERIFRASIS_FIJAS = {
    'dio a luz', 'dar a luz', 'dió a luz',
    'peso de honra',
    'dar de beber', 'dio de beber', 'dió de beber',
    'pasar la noche', 'pasó la noche', 'pasaron la noche', 'pasé la noche',
    'un poco de',
}


def _es_perifrasis_ok(words):
    """Perífrasis de contenido de exactamente 3 palabras (X + a/de/por/como/con
    + Y): «dio a luz», «peso de honra», «dar de beber». No es arrastre."""
    if len(words) != 3:
        return False
    low = [w.lower().strip('¡!¿?.,;:«»"()') for w in words]
    if (any(w in _COPULAS for w in low) or low[0] in _PRON_SOLO
            or low[0] in TONIC_SUBJ_STEM or low[-1] in _DANGLING_END
            or any(w in ARTICLES_ES for w in low[1:])):
        return False
    return low[1] in _CONECTOR_PERIFRASIS


def check_largo(hw):
    """Un token hebreo = un lexema. En español eso son 1 o 2 palabras; 3 o más
    es raro y hay que revisar (report-only). Se cuenta la glosa del TOKEN
    (raíz + sufijo, como en el visor), NO los prefijos (y/a/el… van aparte y
    «y la tierra» es normal). Caza «su él pies» (raíz 2 + sufijo) igual que
    «porción la comida de» (raíz 4). Se EXCLUYEN las perífrasis de 3 palabras
    («dio a luz», «peso de honra»). También marca raíz de 2 palabras que
    empieza por pronombre sujeto («él pies»): es el mismo error a medio camino."""
    es = (hw.get('es') or '').strip()
    if looks_proper(es):
        return None
    if es.lower() in _PERIFRASIS_FIJAS:
        return None
    stem_words = es.split()
    # raíz de 2 palabras encabezada por pronombre sujeto/tónico: «él pies»
    # (aunque el sufijo aún no sume la 3ª). Mismo hueco que POSES 0b.
    if (len(stem_words) >= 2
            and stem_words[0].lower().strip('¡!¿?.,;:«»"()') in TONIC_SUBJ_STEM
            and morph_root(hw.get('he_morph') or '') == 'SUBS'):
        return (f'raíz de {len(stem_words)} palabras empieza por pronombre '
                f'«{stem_words[0]}» — revisar: «{es}»')
    core = combinar_es(es, prs_es(hw), hw.get('he_morph') or '')
    words = core.split()
    if len(words) < 3:
        return None
    if core.lower() in _PERIFRASIS_FIJAS:
        return None
    if _es_perifrasis_ok(stem_words) and len(words) == 3:
        return None
    low = [w.lower().strip('¡!¿?.,;:«»"()') for w in words]
    if (any(w in _COPULAS for w in low)
            or low[0] in _PRON_SOLO or low[0] in TONIC_SUBJ_STEM
            or low[-1] in _DANGLING_END
            or any(w in ARTICLES_ES for w in low[1:])):
        return (f'token de {len(words)} palabras — revisar arrastre/corrupción: '
                f'«{core}»')
    if _es_perifrasis_ok(words):
        return None
    return f'token de {len(words)} palabras — revisar (raro para un lexema): «{core}»'


# pronombres/clíticos sueltos: si un VERBO queda reducido a uno de estos tras el
# arrastre, el verbo real suele ir DESPUÉS del ';' → no autocorregir (ambiguo).
_PRON_SOLO = {
    'yo', 'tú', 'tu', 'él', 'ella', 'ello', 'nosotros', 'nosotras',
    'vosotros', 'vosotras', 'ustedes', 'ellos', 'ellas', 'usted',
    'me', 'te', 'se', 'nos', 'os', 'les', 'le', 'lo', 'la', 'los', 'las',
}
# conjunción/relativo arrastrado al inicio del segmento bueno ("que conocido")
_LEAD_CONJ = ('que ', 'y ', 'pero ', 'porque ', 'o ', 'ni ', 'e ', 'u ',
              'como ', 'pues ', 'mas ', 'aunque ', 'si ', 'cuando ')


def check_puntocoma(hw):
    """Arrastre RVR: la glosa quedó como «BUENO; resto de cláusula» (p.ej.
    «sus hermanos; y», «declararé; A», «que conocido; la cual»). Recupera el
    segmento útil (lo anterior al ';', sin la conjunción/relativo inicial) como
    AUTOFIX cuando es seguro. Si el resultado sería ambiguo —segmento vacío, o un
    VERBO que quedaría reducido a un pronombre (el verbo real va tras el ';')—
    lo deja SOLO en reporte (suggest=None) para revisión manual.
    Devuelve (detalle, suggest|None) o None."""
    es = hw.get('es')
    if not isinstance(es, str) or ';' not in es:
        return None
    head = es.split(';', 1)[0].strip()
    low = head.lower()
    for lead in _LEAD_CONJ:
        if low.startswith(lead):
            head = head[len(lead):].strip()
            low = head.lower()
            break
    detalle = f'arrastre de cláusula RVR en «{es}»'
    if not head:
        return (detalle + ' (sin segmento recuperable)', None)
    if morph_root(hw.get('he_morph') or '') == 'VERBO' and low in _PRON_SOLO:
        return (detalle + f' — VERBO quedaría «{head}» (pronombre); revisar manual', None)
    return (detalle + f' → «{head}»', ('set_es', head, es))


def check_vacio(hw):
    """Solo la causa fiable: morfología de contenido (SUBS/VERBO/ADJ…) con `es`
    vacío. NO se alarma por prefijos hebreos sin glosa española: la mayoría (ל
    infinitivo/locativo, כ, מ, ה absorbido, etc.) no mapean a una palabra
    separada en español y su vacío es normal → generaba falsos positivos."""
    out = []
    m = hw.get('he_morph') or ''
    es = (hw.get('es') or '').strip()
    if is_content(m) and not es and (hw.get('he_form') or '').strip():
        out.append(('stem', f'{m} sin es'))
    return out


def check_corto(hw):
    """Cut-short (punto 9): radical vacío pero hay prefijo/sufijo con glosa.

    Objetivo: palabras de contenido (verbo/sujeto/sustantivo) que quedaron
    vacías mientras su prefijo/sufijo sí se llenó → render "sus ---", "con ---".
    NO alarma en marcadores de objeto (אֵת H853/H854), cuyo `es` vacío es normal
    y cuyo objeto va en el token siguiente.
    """
    m = hw.get('he_morph') or ''
    es = (hw.get('es') or '').strip()
    st = (hw.get('strongs') or '').strip()
    if st in ('H853', 'H854'):          # marcador de objeto directo
        return None
    if not (hw.get('he_form') or '').strip():
        return None
    # caso 1: radical vacío con prefijo/sufijo → render deja "sus ---"/"con ---"
    if not es:
        pe = [p for p in prefix_es_list(hw) if p.strip()]
        se = prs_es(hw).strip()
        if not (pe or se):
            return None
        if not (is_content(m) or se):
            return None
        frag = ' '.join(pe + ([se] if se else [])).strip()
        return f'radical vacío; render deja «{frag} ---»'
    # caso 2: palabra de contenido reducida a una funcional (falta la palabra real).
    # Se adjunta la palabra PROBABLE (lexema translit. o tu glosa más usada por
    # Strong/esqueleto) para poder recuperar el contenido perdido (R4).
    if morph_root(m) in LEXICAL_ROOTS and not is_nprop_gent(m) \
            and es.lower() in FUNCTION_ONLY:
        sug = _sugerir_lexema(hw.get('he_form'))
        if not sug and estilo_usuario is not None:
            pref = estilo_usuario.preferida(st, m)
            if not pref and (hw.get('he_form') or '').strip():
                pref = estilo_usuario.preferida_sk(consk(hw.get('he_form') or ''), m)
            if pref and pref[0]:
                sug = pref[0]
        extra = f' → probable «{sug}»' if sug else ''
        return (f'{morph_root(m)} glosado solo «{es}» — falta la palabra de '
                f'contenido{extra}')
    return None


def check_concord(hw):
    """Concordancia en español:
      · artículo (el/la/los/las) vs género-número del sustantivo;
      · artículo + demostrativo que DISCREPAN en género/número («los estas»→«las»);
      · posesivo singular (su/mi/tu) ante sustantivo PLURAL («su ojos»→«sus ojos»).
    Devuelve lista de (detalle, suggest)."""
    out = []
    stem = (hw.get('es') or '').strip()
    m = hw.get('he_morph') or ''
    for i, pe in enumerate(prefix_es_list(hw)):
        art = pe.strip().lower()
        if art not in ARTICLES_ES or not stem:
            continue
        first = stem.split()[0].lower()
        # (a) artículo + demostrativo: solo error si DISCREPAN género/número.
        #     «el aquel»/«la esta»/«las esas» (concuerdan) son válidos en este
        #     interlineal (הַ + demostrativo). «los estas» (m.pl vs f.pl) es error.
        if first in DEMO_GN:
            if ART_GN.get(art) != DEMO_GN[first]:
                good = GN_ART.get(DEMO_GN[first])
                if good:
                    out.append((f'artículo {art!r} no concuerda con demostrativo '
                                f'{first!r} → {good!r}', ('pfx_set', i, good, pe)))
            continue
        # (b) artículo ante palabra capitalizada (transliteración/nombre): en este
        #     interlineal el usuario usa artículo con transliteraciones de sustantivos
        #     comunes («la Adamáh», «el Goy», «la Néfesh», «el 'Elohim», «la Mitzrit»)
        #     y con topónimos/ríos que en español llevan artículo → NO se marca.
        if looks_proper(stem):
            continue
        # (b2) nombre propio / gentilicio (aunque su glosa esté en minúscula, p.ej.
        #      «eufrates»): el artículo con nombres propios/gentilicios es
        #      idiosincrático (el Éufrates, los amalecitas) → no se autocorrige.
        if is_nprop_gent(m):
            continue
        # (c) género/número del artículo vs SUSTANTIVO (no adjetivos/numerales
        #     —«los cuarenta días» concuerda con el nombre, no con el numeral— ni
        #     verbos/participios sustantivados: «el que repta»)
        if morph_root(m) == 'SUBS' and _articulable(first):
            exp = expected_article(stem)
            if exp and art != exp:
                out.append((f'artículo {art!r} ≠ género/número de {stem!r} → {exp!r}',
                            ('pfx_set', i, exp, pe)))
            # (c2) desacuerdo de NÚMERO aunque el género sea desconocido: nombres
            #      que terminan en consonante («árbol», «rey») dan es_gender=None,
            #      así que (c) no dispara. El número lo fija la MORFOLOGÍA HEBREA
            #      (autoritativa), NO el heurístico español (que ve «-es/-s» como
            #      plural y crea falsos «los eufrates», «los país»). Conserva el
            #      género del artículo actual. (Gén 23:17 «los árbol»)
            elif exp is None and first not in SINGULAR_IN_S:
                heb_num = 'p' if ('.PL' in m or '.DU' in m) else 's'
                art_num = 'p' if art in ('los', 'las') else 's'
                if art_num != heb_num:
                    art_gen = 'f' if art in ('la', 'las') else 'm'
                    fix = {('m', 's'): 'el', ('m', 'p'): 'los',
                           ('f', 's'): 'la', ('f', 'p'): 'las'}[(art_gen, heb_num)]
                    out.append((f'artículo {art!r} ({art_num}) ≠ número hebreo '
                                f'({heb_num}) de {stem!r} → {fix!r}',
                                ('pfx_set', i, fix, pe)))
        # (c) posesivo-prefijo singular ante sustantivo plural (morf .PL/.DU)
    for i, pe in enumerate(prefix_es_list(hw)):
        w = pe.strip().lower()
        if w in POSS_SG2PL and stem and ('.PL' in m or '.DU' in m):
            if es_number(stem.split()[0].lower()) == 'p':
                out.append((f'posesivo {w!r} ante sustantivo plural {stem!r} → '
                            f'{POSS_SG2PL[w]!r}', ('pfx_set', i, POSS_SG2PL[w], pe)))
    # (d) sufijo posesivo singular con sustantivo poseído PLURAL → plural
    ps = prs_es(hw).strip().lower()
    if ps in POSS_SG2PL and stem and ('.PL' in m or '.DU' in m):
        if es_number(stem.split()[0].lower()) == 'p':
            out.append((f'sufijo posesivo {ps!r} con sustantivo plural {stem!r} → '
                        f'{POSS_SG2PL[ps]!r}', ('set_prs', POSS_SG2PL[ps], prs_es(hw))))
    return out


_PRON3_SUBJ = {'él', 'ella', 'ellos', 'ellas'}


def check_pron(hw):
    """(a) preposición + pronombre redundante en la raíz ante sufijo pronominal;
    (b) presentativo הִנֵּה + sufijo → idiom (heme aquí…);
    (c) pronombre personal independiente PRON.PERS de 3ª: género/número por
    morfología (הִוא pentateucal con vav = femenino «ella»). Lista de (detalle, sug)."""
    out = []
    stem = (hw.get('es') or '').strip()
    pm = prs_morph(hw)
    m = hw.get('he_morph') or ''
    # solo hay duplicación si el sufijo APORTA un pronombre (es no vacío);
    # si el sufijo va vacío, la raíz "para ti" es correcta y no se toca.
    # NUNCA sobre un VERBO: un verbo con sufijo pronominal lleva OBJETO legítimo
    # (תִּתִּי «mi dar / que yo dé»); despojar el pronombre lo mutila (Gén 29:19).
    if stem and prs_es(hw).strip() and morph_root(m) != 'VERBO' \
            and is_pron_suffix(pm):
        words = stem.split()
        if len(words) >= 2 and words[-1].lower() in PRON_TAIL:
            head = ' '.join(words[:-1])
            if head.split()[0].lower() in PREP_HEADS:
                out.append((f'raíz {stem!r} lleva pronombre ante sufijo {pm}; raíz→{head!r}',
                            ('set_es', head, stem)))
    if m.startswith('PART.DEM') and pm.upper().startswith('PRS') and 'aqu' in stem.lower():
        idiom = hinneh_idiom(pm)
        if idiom and render_token(hw).lower() != idiom.lower():
            out.append((f'presentativo+sufijo {pm}: {render_token(hw)!r} → {idiom!r}',
                        ('idiom', idiom, stem)))
    # (c) PRONOMBRE PERSONAL independiente (PRON.PERS): el género y el número los da
    #     la MORFOLOGÍA, no el esqueleto. הִוא (grafía pentateucal escrita con vav,
    #     igual que el masculino הוּא) es FEMENINO por morfología (P3.F.SG) → «ella»,
    #     aunque parezca masculino (Gén 26:7 quedó «él»). AUTOFIX estrecho: solo 3ª
    #     persona y solo si la glosa es EXACTAMENTE otro pronombre-sujeto de 3ª
    #     (él/ella/ellos/ellas) que CONTRADICE el género/número de la morfología;
    #     nunca toca glosas contextuales (más de una palabra) ni 1ª/2ª persona.
    md = '.' + m + '.'
    if '.PERS.' in md and '.P3.' in md and stem.lower() in _PRON3_SUBJ:
        plu = '.PL.' in md or '.DU.' in md
        fem = '.F.' in md
        want = ('ellas' if fem else 'ellos') if plu else ('ella' if fem else 'él')
        if stem.lower() != want:
            tgt = want[:1].upper() + want[1:] if stem[:1].isupper() else want
            out.append((f'pronombre personal {m} glosado {stem!r}; el género/número '
                        f'lo fija la morfología → {tgt!r} (הִוא pentateucal con vav '
                        f'sigue siendo femenino)', ('set_es', tgt, stem)))
    return out


_IMPERF_RE = re.compile(r'(aba|abas|ábamos|abais|aban|ía|ías|íamos|íais|ían)$')
_SUBJ_RE = re.compile(r'(ara|aras|áramos|aran|ase|ases|ásemos|asen|are|ares|'
                      r'aren|iera|ieras|ieran|iese|ieses|iesen|iere|ieren)$')
# cuantificadores / adjetivos / participios que NO son sustantivos: si tras quitar
# el pronombre la raíz empieza por uno de estos, NO es un nombre limpio → reporte.
_NO_NOMBRE = {
    'todos', 'todas', 'toda', 'todo', 'mucho', 'mucha', 'muchos', 'muchas',
    'poco', 'poca', 'pocos', 'pocas', 'otro', 'otra', 'otros', 'otras',
    'mismo', 'misma', 'mismos', 'mismas', 'tanto', 'tanta', 'ambos', 'ambas',
    'muerto', 'muerta', 'muertos', 'muertas', 'vivo', 'viva', 'lleno', 'llena',
    'junto', 'juntos', 'juntas', 'solo', 'sola', 'entero', 'entera',
}


def _rest_es_nombre_seguro(rest: str) -> bool:
    """True solo si `rest` es UN sustantivo español limpio (una palabra, no verbo
    ni cuantificador/adjetivo/participio). Blinda el autofix de pronombre-en-raíz
    para que NUNCA produzca basura como «su fueron», «su bebía», «sus todos»: esos
    casos (raíz entera corrupta con verbo/oración) quedan en REPORTE."""
    parts = rest.split()
    if len(parts) != 1:
        return False
    w = parts[0].lower()
    if not re.fullmatch(r"[a-záéíóúüñ]+", w) or w in _NO_NOMBRE:
        return False
    if (_INF_RE.match(w) or _VERBISH_RE.search(w) or _PRET_IND_RE.search(w)
            or _FUT_RE.search(w) or _IMPERF_RE.search(w) or _SUBJ_RE.search(w)
            or w.endswith('ndo')):
        return False
    return True


# Parentesco SG en vocativo editorial: posesivo TÓNICO postpuesto («hijo mío»,
# «padre mío»), no el proclítico «mi hijo». Lo fijó el usuario en Gén 27 (verdes).
_PARENTESCO_TONICO = {
    'hijo': 'hijo mío', 'hija': 'hija mía',
    'padre': 'padre mío', 'madre': 'madre mía',
    'hermano': 'hermano mío', 'hermana': 'hermana mía',
}
_PARENTESCO_BASE = set(_PARENTESCO_TONICO)


def check_parentesco_tonico(hw):
    """AUTOFIX (POSES). Sufijo PRS.P1 + parentesco SG glosado «mi X» / «X»+mi →
    «X mío/mía» fusionado (limpia el sufijo). Solo 1ª persona; no toca «su hijo».
    También normaliza «hijo mio» (sin tilde) → «hijo mío»."""
    m = hw.get('he_morph') or ''
    if morph_root(m) != 'SUBS':
        return None
    pm = prs_morph(hw)
    if not is_pron_suffix(pm) or suffix_person(pm) != 1:
        return None
    if '.PL' in (pm or '').upper() or '.DU' in (pm or '').upper():
        return None
    stem = (hw.get('es') or '').strip()
    ps = prs_es(hw).strip()
    if not stem:
        return None
    # ¿? final (p.ej. «hijo mío?»): conservar marca interrogativa
    q = ''
    core = stem
    if core.endswith('?'):
        q = '?'
        core = core[:-1].rstrip()
    words = core.split()
    if not words:
        return None
    low = [w.lower() for w in words]

    def _target_for(base):
        t = _PARENTESCO_TONICO.get(base)
        return (t + q) if t else None

    # a) ya postpuesto sin tilde: «hijo mio» → «hijo mío»
    if len(words) == 2 and low[0] in _PARENTESCO_BASE and low[1] in ('mio', 'mia', 'míos', 'mias'):
        tgt = _target_for(low[0])
        if tgt and stem != tgt:
            if ps:
                return (f'parentesco vocativo «{stem}» → «{tgt}» (tilde + limpia sufijo)',
                        ('idiom', tgt, stem))
            return (f'parentesco vocativo «{stem}» → «{tgt}» (tilde RAE)',
                    ('set_es', tgt, stem))
        if tgt and stem == tgt and ps:
            return (f'parentesco vocativo ya «{tgt}»; sufijo {ps!r} residual → limpiar',
                    ('idiom', tgt, stem))
        return None
    # b) proclítico en raíz: «mi hijo» (+suf opcional)
    if len(words) == 2 and low[0] == 'mi' and low[1] in _PARENTESCO_BASE:
        tgt = _target_for(low[1])
        if not tgt:
            return None
        return (f'parentesco vocativo «{stem}» → «{tgt}» (posesivo tónico postpuesto)',
                ('idiom', tgt, stem))
    # c) raíz solo nombre + sufijo «mi»: «hijo»+mi → «hijo mío»
    if len(words) == 1 and low[0] in _PARENTESCO_BASE and ps.lower() == 'mi':
        tgt = _target_for(low[0])
        if not tgt:
            return None
        return (f'parentesco vocativo «{stem}»+«{ps}» → «{tgt}» (fusiona y limpia sufijo)',
                ('idiom', tgt, stem))
    return None


def check_poses(hw):
    """Posesivos apilados (raíz + sufijo). Corrige SOLO si la persona de la raíz
    coincide con la del sufijo (limpia el sufijo redundante); si discrepan, reporta."""
    # Vocativo parentesco (hijo/padre mío) ANTES del resto: el proclítico «mi X»
    # es el error a corregir, no un apilamiento clásico. También normaliza tilde.
    r_par = check_parentesco_tonico(hw)
    if r_par:
        return r_par
    stem = (hw.get('es') or '').strip()
    ps = prs_es(hw).strip()
    if not stem or not ps:
        return None
    # sufijo NO pronominal (he/nun paragógico, locativo direccional): no es
    # posesivo → no hay apilamiento que corregir (el motor hebreo lo distingue).
    if not is_pron_suffix(prs_morph(hw)):
        return None
    m = hw.get('he_morph') or ''
    words = stem.split()
    w0 = words[0].lower()
    # (0) POSESIVO LARGO/TÓNICO incrustado en la raíz (mío/mía/tuyo/suyo/nuestro/
    #     vuestro…): SIEMPRE espurio cuando hay sufijo pronominal (el posesivo
    #     correcto lo aporta el sufijo). Produce el doble visible «mi mío señor».
    #     Se quita de la raíz; el sufijo conserva el posesivo (CONCORD ajusta el
    #     número: p.ej. «tu» ante plural → «tus»).
    #     AUTOFIX solo si es SEGURO: (a) sustantivo (SUBS) —los participios con
    #     clítico objeto o las PREP mal alineadas se dejan en reporte—, y (b) tras
    #     quitar el posesivo el resto empieza por PALABRA DE CONTENIDO (no otro
    #     posesivo/artículo/preposición/funcional, p.ej. «mía mío», «mío junto»).
    #     En el resto de casos → solo reporte.
    if w0 in LONG_POSS:
        rest = ' '.join(words[1:]).strip()
        rw0 = rest.split()[0].lower() if rest else ''
        safe = (rest and morph_root(m) == 'SUBS'
                and rw0 not in LONG_POSS and rw0 not in POSSESSIVES
                and rw0 not in ARTICLES_ES and rw0 not in PREP_ES_HEADS
                and rw0 not in FUNC_WORDS)
        if safe:
            return (f'posesivo largo/tónico {words[0]!r} incrustado en raíz '
                    f'«{stem}» (doble con sufijo {ps!r}) → quitar → «{rest}»',
                    ('set_es', rest, stem))
        return (f'posesivo largo/tónico {words[0]!r} en raíz «{stem}» '
                f'(doble con sufijo {ps!r}); resto no autofixable — revisar', None)
    # (0b) PRONOMBRE SUJETO/TÓNICO incrustado en la raíz de un SUBS con sufijo
    #      pronominal («él pies» + suf «su» = doble del mismo ו 3ms → render
    #      «su él pies»). Un pronombre sujeto ANTE un sustantivo siempre es espurio.
    #      Se quita y el posesivo correcto se RECONSTRUYE desde el sufijo hebreo
    #      (persona+número), concordando con el sustantivo (dual «pies» → «sus»);
    #      se limpia el sufijo. AUTOFIX solo si tras quitarlo el resto empieza por
    #      palabra de contenido (no otro pronombre/posesivo/artículo/prep/funcional).
    if w0 in TONIC_SUBJ_STEM and morph_root(m) == 'SUBS':
        rest = ' '.join(words[1:]).strip()
        rw0 = rest.split()[0].lower() if rest else ''
        sp = suffix_person(prs_morph(hw))
        own_f = suffix_owner_number(prs_morph(hw))
        # AUTOFIX solo si el resto es UN sustantivo limpio (no verbo/oración): así
        # «él pies»→«sus pies» pero «ella fueron»/«ellos todos» → reporte.
        safe = (_rest_es_nombre_seguro(rest) and rw0 not in POSSESSIVES
                and rw0 not in LONG_POSS and rw0 not in TONIC_SUBJ_STEM
                and rw0 not in ARTICLES_ES and rw0 not in PREP_ES_HEADS
                and rw0 not in FUNC_WORDS)
        if safe and sp is not None:
            g = es_gender(rw0)
            nnum = es_number(rw0)
            newstem = f'{spanish_poss(sp, own_f, g, nnum)} {rest}'
            if newstem != stem:
                return (f'pronombre sujeto/tónico {words[0]!r} incrustado en raíz '
                        f'«{stem}» (doble del sufijo {prs_morph(hw)}) → «{newstem}» '
                        f'(+ limpiar sufijo)',
                        ('poss_rehome', stem, newstem, ps))
        return (f'pronombre sujeto/tónico {words[0]!r} en raíz «{stem}» '
                f'(doble con sufijo {ps!r}); no autofix seguro — revisar', None)
    pfirst = w0
    p1 = poss_person(pfirst)
    p2 = poss_person(ps.lower())
    if p1 is None or p2 is None:
        return None
    # el visor deduplica cuando el sufijo repite una palabra ya presente en la
    # raíz (combineEsWithSuffix): en ese caso NO hay doble visible → no se marca.
    if ps.lower() in [w.lower() for w in stem.split()]:
        return None
    sp = suffix_person(prs_morph(hw))
    own_s = poss_owner_number(pfirst)
    own_f = suffix_owner_number(prs_morph(hw))
    # ── caso REDUNDANTE seguro (comportamiento histórico, INTACTO) ──
    #    misma persona Y sin conflicto de número de poseedor → el posesivo de la
    #    raíz ya representa correctamente al sufijo → limpiar el sufijo redundante
    #    (p.ej. «sus ovejas» 3ª pers. + sufijo «su»: own_s=None → sin conflicto).
    if sp is not None and p1 == sp and not (own_s and own_f and own_s != own_f):
        return (f'posesivos apilados {pfirst!r}+{ps!r}; sufijo redundante → limpiar',
                ('clear_prs', ps))
    # ── EL SUFIJO HEBREO ES LA AUTORIDAD (BUG2 número + R8 persona) ──
    #    La raíz trae un posesivo que NO concuerda con el sufijo: distinta persona
    #    («su mi padre» = 3ª sufijo vs 1ª raíz) o mismo persona pero distinto número
    #    de poseedor («nuestro padre» sufijo 1ª PL vs raíz «mi» 1ª SG → renderiza
    #    «MI padre» tras un clear_prs erróneo). En ambos casos el arrastre RVR de la
    #    raíz es espurio: se reconstruye el posesivo correcto DESDE el sufijo
    #    (persona+número), concordando con el sustantivo, y se limpia el sufijo.
    #    AUTOFIX solo si es SEGURO: SUBS y, tras quitar el posesivo, el resto empieza
    #    por PALABRA DE CONTENIDO (no otro posesivo/artículo/prep/funcional).
    rest = ' '.join(words[1:]).strip()
    rw0 = rest.split()[0].lower() if rest else ''
    safe = (rest and morph_root(m) == 'SUBS'
            and rw0 not in POSSESSIVES and rw0 not in LONG_POSS
            and rw0 not in ARTICLES_ES and rw0 not in PREP_ES_HEADS
            and rw0 not in FUNC_WORDS)
    if safe and sp is not None:
        g = es_gender(rw0)
        nnum = es_number(rw0)
        newp = spanish_poss(sp, own_f, g, nnum)
        newstem = f'{newp} {rest}'
        if newstem != stem:
            return (f'posesivo raíz {pfirst!r} no concuerda con sufijo {prs_morph(hw)} '
                    f'{ps!r} (el sufijo hebreo manda) → «{newstem}» (+ limpiar sufijo)',
                    ('poss_rehome', stem, newstem, ps))
    return (f'posesivo raíz {pfirst!r} vs sufijo {prs_morph(hw)} {ps!r} '
            f'(no autofix seguro — revisar)', None)


def check_morph_mismatch(hw):
    """Incoherencia entre la morfología (lado hebreo) y la clase de la glosa ES.

    Caso principal: una PREPOSICIÓN hebrea cuya glosa NO empieza por preposición
    ni por palabra funcional → casi siempre un homógrafo mal alineado
    (p.ej. עִם H5973 «con» confundido con עַם H5971 «pueblo» → glosa "pueblo").
    Es una señal, no un autofix: elegir la palabra correcta (y a veces corregir
    el Strong) requiere criterio, por eso solo se reporta.

    También caza HOMÓGRAFOS funcionales conocidos (adverbios/partículas que el
    spider glosa como verbo u otra clase): שָׁם «allí» (no el verbo שׂם «poner»),
    כֵּן «así», לוּ «si tan solo / ojalá». Se marca si la glosa no contiene la
    lectura esperada. Reafirmación motor · Gén 23:13 «שם→puso», «לו→y»."""
    m = hw.get('he_morph') or ''
    ck = consk(hw.get('he_form') or '')
    hg = _HOMOGRAFOS_FUNC.get((ck, morph_root(m)))
    if hg:
        head, nota = hg
        esr = (hw.get('es') or '').strip().lower()
        if esr and head not in esr:
            return (f'{nota}; glosa actual {hw.get("es")!r} — esperado «{head}»')
    esr = (hw.get('es') or '').strip().lower()
    es_raw = (hw.get('es') or '').strip()
    # NOMBRE DIVINO en MINÚSCULA (report-only). H430 אֱלֹהִים / H410 אֵל /
    # H433 אֱלוֹהַּ glosados «dios»/«el». Autofixarlo sería peligroso: en Génesis
    # aparecen DIOSES AJENOS (plural pagano, «dioses extraños» 35:2/35:4) que SÍ van
    # en minúscula. Se REPORTA para que decidas caso por caso (Dios verdadero →
    # «Dios»/«ʼElohim»/«ʼEl»). Gén 26:24, 28:13/21, 31:5/29/42/53, 32:24…
    st_div = (hw.get('strongs') or '').strip()
    if st_div in ('H430', 'H410', 'H433') and es_raw and es_raw[0].islower():
        w0d = esr.split()[0] if esr else ''
        # H430 absoluto «dios» ya lo AUTOFIXEA TRANSLIT (→ 'Elohim, tu forma exacta):
        # aquí solo se REPORTA lo que TRANSLIT NO toca — el constructo «dios de»
        # (grafía 'Elohei, a mano) y H410/H433 — para no doble-listar el autofix.
        if w0d in ('dios', 'el') and not (st_div == 'H430' and check_translit_lexema(hw)):
            sug = ("«ʼElohim de …» / «ʼElohei …» (constructo, a mano)"
                   if st_div == 'H430' and '.C' in m
                   else "«Dios»/«ʼElohim»/«ʼEl» si es el Dios verdadero")
            return (f'posible nombre divino en minúscula ({st_div}: '
                    f'{"אֱלֹהִים" if st_div == "H430" else "אֵל/אֱלוֹהַּ"}) glosado '
                    f'{hw.get("es")!r} → {sug} (déjalo en minúscula si son dioses ajenos)')
    # גוע (H1478): «expirar/fallecer». No lleva «espíritu» (no aparece רוּחַ/Ruaj).
    if 'גוע' in ck and 'espíritu' in esr:
        return ('גוע = «expiró/falleció» — no añadir «espíritu» (no hay רוּחַ en el texto)')
    # שְׁנֵי (ADJ.M.DU.C, constructo dual) glosado «escarlata»: שָׁנִי (H8144,
    # escarlata) es OTRO lexema (sustantivo). Aquí es «dos de» / «años de».
    if ck == 'שני' and morph_root(m) == 'ADJ' and 'escarlata' in esr:
        return ('שְׁנֵי dual constructo → «dos de» o «años de»; «escarlata» (שָׁנִי) es otro lexema')
    # ברך en HIFIL = «hacer arrodillar» (causativo). El Hifil NUNCA significa
    # bendecir (eso es el Piel). Si aparece glosado como bendecir/amparar es un
    # homógrafo mal leído → «arrodillarse / hacer arrodillar» (p.ej. Gén 24:11
    # וַיַּבְרֵךְ הַגְּמַלִּים = «hizo arrodillar los camellos»).
    if ('ברך' in ck or 'ברכ' in ck) and 'HIF' in m and \
            any(s in esr for s in ('bendi', 'bendec', 'bendij', 'ampar')):
        return ('ברך en Hifil = «hacer arrodillar» (causativo); no «bendecir/amparar» '
                '(eso es el Piel)')
    # נגד H5046 en HIFIL/HOFAL = «contar/declarar/anunciar/informar» (higgid).
    # NUNCA significa «saber» (eso es ידע; «hacer saber» es su Hifil hodía). Si
    # aparece glosado «saber/supo/sabido…» es confusión de lexema → contar/
    # declarar (Gén 24:28 וַתַּגֵּד = «contó»). Se gatea por STRONG H5046, no por
    # esqueleto: la נ inicial ASIMILA en imperfecto/Hifil (תַּגֵּד→תגד, הִגִּיד→הגד),
    # así que el esqueleto casi nunca contiene «נגד». Report-only (el verbo/tiempo
    # exacto lo eliges tú).
    if (hw.get('strongs') or '').strip() == 'H5046' and morph_root(m) == 'VERBO' \
            and any(w.startswith(('saber', 'sabe', 'sabr', 'sabid', 'sup', 'sepa',
                                  'sepe', 'sepá'))
                    for w in esr.split()):
        return ('נגד en Hifil/Hofal = «contar/declarar/anunciar/informar»; no '
                '«saber» (eso es ידע) → probable «contó/declaró/anunció»')
    # אָחוֹת H269 «hermana» (SUBS femenino, esqueleto אחת/אחות) glosada «uno/una/
    # un» = confusión con אֶחָד/אַחַת H259 «uno». Debe ser «hermana» (+ posesivo).
    # SALVO el modismo אִשָּׁה אֶל־אֲחֹתָהּ «una a otra» (cortinas Éx 26, Ez), donde
    # אֲחֹת = «otra» —por eso es REPORTE y NO autofix: distinguir hermana/otra
    # exige el contexto (lo decides tú). La morfología SUBS.F.SG(.C) la separa del
    # NUMERAL אַחַת (que iría como ADJ/NUM). Gén 24:30 «su uno»→«su hermana».
    if morph_root(m) == 'SUBS' and '.F.' in m and ck in ('אחת', 'אחות') \
            and esr.split() and esr.split()[0] in ('uno', 'una', 'un', 'unos', 'unas'):
        return ('אָחוֹת = «hermana» (no «uno/una»; eso es אֶחָד/אַחַת) → «hermana» '
                '+ posesivo — salvo el modismo אִשָּׁה אֶל־אֲחֹתָהּ «una a otra»')
    # RECORRIDO: un VERBO glosado EXACTAMENTE como preposición/conjunción suelta.
    # La glosa de una ficha contigua (típicamente la לְ «a/para/por») invadió el
    # verbo, que quedó sin su glosa léxica (p.ej. Gén 24:13 שְׁאֹב INFC → «por»).
    if morph_root(m) == 'VERBO' and esr in _VERBO_RECORRIDO:
        return (f'VERBO glosado como palabra funcional «{esr}» — probable recorrido '
                f'de una preposición contigua (לְ «a/para/por»); falta la glosa del verbo')
    # INFINITIVO hebreo (INFA/INFC) cuya glosa base es un SUSTANTIVO DERIVADO en
    # vez del verbo (שקה INFC «abrevadero» → debe ser «abrevar»/«abrevarlo»,
    # Gén 24:19). Hueco que NINGÚN otro check cubría: check_morfo excluye los
    # infinitivos por diseño; check_enclit/RENDER solo miran clíticos (y aquí el
    # clítico va en prs_suffix). Reporte + sugerencia léxica (el verbo lo eliges
    # tú). Cubre también el clítico antepuesto en la raíz («lo abrevadero»).
    if morph_root(m) == 'VERBO' and ('INFC' in m or 'INFA' in m) and esr:
        te = esr.split()
        content = ' '.join(te[1:]) if (len(te) >= 2 and te[0] in _OBJ_CLITICS) else esr
        if content and ' ' not in content:
            base_c = _quitar_enclitics(content)
            if (not _INF_RE.match(base_c) and not base_c.endswith('ndo')
                    and base_c.endswith(_INF_NOUN_SUF)
                    and not looks_proper(es_raw) and not is_nprop_gent(m)):
                sug = _sugerir_lexema(hw.get('he_form'))
                extra = f' → probable «{sug}»' if sug else ''
                return (f'infinitivo hebreo ({m}) glosado como sustantivo derivado '
                        f'«{hw.get("es")}» — falta el infinitivo{extra}')
    # SUSTANTIVO/ADJETIVO hebreo glosado con un VERBO CONJUGADO (forma FINITA). Un
    # SUBS/ADJ jamás se glosa con una conjugación; es arrastre RVR u homógrafo
    # (Gén 24:22 מִשְׁקָל SUBS «peso» quedó «pesaban»; 40:5 חֲלוֹם «sueño»→«soñó»;
    # 44:20 יֶלֶד «niño»→«nació»). Se ignora posesivo/artículo inicial y se mira el
    # núcleo. Desinencias INEQUÍVOCAS (pretérito -ó/-aron, imperfecto -aban/-ían,
    # 2ª sg -aste/-iste…): NO usa el futuro (-rás colisiona con atrás/detrás). Se
    # EXCLUYEN: transliteraciones (es_source «translit_*»: «nafshó», נפש), no-verbos
    # que acaban como conjugación (_NO_ES_VERBO: «triste»), infinitivos
    # (nominalización «el andar»), gerundios, nombres propios y gentilicios.
    # Report-only + sugerencia léxica (el sustantivo correcto lo eliges tú).
    if morph_root(m) in ('SUBS', 'ADJ') and esr and not is_nprop_gent(m) \
            and not looks_proper(es_raw) \
            and not (hw.get('es_source') or '').startswith('translit'):
        te = esr.split()
        idx = 0
        while idx < len(te) and (te[idx] in POSSESSIVES or te[idx] in LONG_POSS
                                 or te[idx] in ARTICLES_ES
                                 or te[idx] in _LEAD_CLITICS):
            idx += 1
        nucleo = te[idx] if idx < len(te) else ''
        if (nucleo and len(nucleo) >= 4 and nucleo not in _NO_ES_VERBO
                and not _INF_RE.match(nucleo) and not nucleo.endswith('ndo')
                and (_VERBISH_RE.search(nucleo) or _PRET_IND_RE.search(nucleo))):
            sug = _sugerir_lexema(hw.get('he_form'))
            extra = f' → probable «{sug}»' if sug else ''
            return (f'{morph_root(m)} ({m}) glosado como verbo conjugado '
                    f'«{nucleo}» — falta el sustantivo{extra}')
    if morph_root(m) != 'PREP':
        return None
    es = (hw.get('es') or '').strip().lower()
    if not es:
        return None
    head = es.split()[0].strip('¿¡«»""\'().,;:')  # ignora signos de apertura
    if head in PREP_ES_HEADS or head in FUNC_WORDS or head in POSSESSIVES:
        return None
    return (f'morf PREP pero la glosa {hw.get("es")!r} no es preposicional '
            f'(¿homógrafo? p.ej. עם con↔pueblo)')


def _con_pronombre(prs_m):
    """«con» + pronombre preposicional español a partir de la MORFOLOGÍA del
    sufijo PRS (persona/número/género), no de su glosa. Fusiona 1ª sg→«conmigo»,
    2ª sg→«contigo»; el resto va «con + tónico» (con él/ella/nosotros/ustedes/
    ellos/ellas). Devuelve None si no hay sufijo pronominal (PRS.*). Se usa para
    reconstruir עִם+sufijo de forma robusta aunque la glosa del sufijo esté
    corrupta («su», «te», «a mí»…). 2ª pl → «ustedes» (español neutro/LatAm)."""
    u = (prs_m or '').upper()
    if not u.startswith('PRS'):
        return None
    per = '1' if 'P1' in u else '2' if 'P2' in u else '3' if 'P3' in u else ''
    pl = ('.PL' in u or u.endswith('PL') or '.DU' in u)
    fem = ('.F.' in u or u.endswith('.F'))
    if per == '1':
        return 'con nosotros' if pl else 'conmigo'
    if per == '2':
        return 'con ustedes' if pl else 'contigo'
    if per == '3':
        if pl:
            return 'con ellas' if fem else 'con ellos'
        return 'con ella' if fem else 'con él'
    return None


# Reconstrucción «con+pronombre» desde la GLOSA del sufijo cuando la morfología
# del sufijo falta (עִמָּדִי sin PRS.* pero con prs_suffix.es «mí»). Complementa a
# _con_pronombre (que usa la morfología). Fusiona conmigo/contigo/consigo.
_SUF_ES_A_CON = {
    'mí': 'conmigo', 'mi': 'conmigo', 'me': 'conmigo',
    'ti': 'contigo', 'te': 'contigo',
    'él': 'con él', 'ella': 'con ella', 'sí': 'consigo',
    'nosotros': 'con nosotros', 'nosotras': 'con nosotras',
    'ustedes': 'con ustedes', 'vosotros': 'con ustedes', 'vosotras': 'con ustedes',
    'ellos': 'con ellos', 'ellas': 'con ellas',
}
# Glosas de CONTENIDO imposibles para una preposición עִם (homógrafos del
# esqueleto עמ): עַם H5971 «pueblo» y עמד H5975 «estar de pie/parado». Una PREP
# jamás significa eso → autofix a «con»(+pronombre).
_IM_HOMOGRAF_WRONG = ('pueblo', 'pueblos', 'parado', 'parados',
                      'parada', 'paradas')


def check_homograf(hw):
    """Homógrafos funcionales deterministas glosados con el verbo EQUIVOCADO.
    AUTOFIX seguro y ACOTADO: solo corrige cuando la glosa actual es literalmente
    un verbo de «poner» (שׂם/שׂים) sobre un token que morfológicamente es el
    adverbio שָׁם/שָׁמָּה (ADV → «allí»/«allá») o el sustantivo שֵׁם (SUBS →
    «nombre»). NUNCA toca variantes adverbiales válidas («allá», «donde»,
    «en ella») ni el verbo real (VERBO.* se queda como está).

    Reafirmación motor (Gén 25:10 שָׁמָּה «puso»→«allí»): error sistemático en
    todo el corpus donde el spider confundió שָׁם (allí) con שָׂם (puso)."""
    m = hw.get('he_morph') or ''
    # pliega letras finales (ך ם ן ף ץ → כ מ נ פ צ): שָׁם usa mem FINAL (ם) pero
    # שָׁמָּ usa mem regular (מ); ambos deben normalizar al mismo esqueleto.
    ck = consk(hw.get('he_form') or '').translate(_FINALES)
    es = (hw.get('es') or '').strip()
    st = (hw.get('strongs') or '').strip()
    # ── אֵת H853 = marcador de OBJETO DIRECTO (acusativo), HOMÓGRAFO del אֵת H854
    #    «con». Con sufijo pronominal glosado «con» es la confusión H853↔H854: el
    #    acusativo NUNCA es «con». Tu uso DOMINANTE en el corpus es «a» + tónico
    #    («a él/a ella/a ti/a ellos»); el pronombre lo fija la MORFOLOGÍA del sufijo
    #    (autoridad). Autofix con la op idiom (reconstruye render y limpia sufijo).
    if st == 'H853':
        _prs = hw.get('prs_suffix') or {}
        _prsm = _prs.get('he_morph') or ''
        _head = es.split()[0].lower() if es else ''
        if _prsm.upper().startswith('PRS') and _head == 'con':
            _pron = _tonico_de_sufijo(_prsm, _prs.get('es'))
            if _pron:
                target = f'a {_pron}'
                if es[:1].isupper():
                    target = target[:1].upper() + target[1:]
                return (f'אֵת H853 (acusativo) glosado «{es}» — confusión con H854 «con»; '
                        f'objeto directo → «{target}» (pronombre de la morfología)',
                        ('idiom', target, hw.get('es') or ''))
    # ── הִנֵּה H2009 «he aquí»: glosado solo «aquí»/«ahí» pierde el deíctico
    #    presentativo (error sistemático en todo el corpus). Solo SIN sufijo
    #    pronominal (con sufijo → הִנֵּנִי «heme aquí», lo maneja hinneh_idiom).
    if st == 'H2009' and not prs_morph(hw):
        low = es.lower().strip(' .,;:¡!¿?')
        if low in ('aquí', 'aqui', 'ahí', 'ahi'):
            nuevo = 'He aquí' if es[:1].isupper() else 'he aquí'
            return (f'הִנֵּה H2009 glosado «{es}» → «he aquí»',
                    ('set_es', nuevo, hw.get('es') or ''))
    # ── verbo de PARTO ילד (H3205) TRUNCADO (RVR «dar a luz» cortado): recupera
    #    la locución completa con el TIEMPO correcto. Dos formas de corte, ambas
    #    imposibles como glosa legítima de este VERBO → autofix seguro:
    #      · el complemento suelto «luz»/«a luz»/«la luz» (Gén 25:2/25:12);
    #      · el verbo «dar» suelto «dio/dió/dieron/dará/darán/dar/da» (± «a»):
    #        Gén 24:24 יָלְדָה glosado «dio» → «dio a luz».
    #    La guarda es_yalad (H3205 / esqueleto ילד/לד) evita tocar el verbo נתן
    #    «dar» real. El tiempo lo fija la morfología, no el fragmento.
    _YALAD_FRAG = ('luz', 'a luz', 'la luz',
                   'dio', 'dió', 'dieron', 'dará', 'darán', 'dar', 'da',
                   'dio a', 'dió a', 'dieron a', 'dará a', 'darán a',
                   'dar a', 'da a')
    if morph_root(m) == 'VERBO' and es.lower() in _YALAD_FRAG:
        st = (hw.get('strongs') or '').strip()
        es_yalad = (st == 'H3205' or 'ילד' in ck
                    or ('לד' in ck and ck[:1] in 'יתאנוה')
                    # INFINITIVO CONSTRUCTO לֶדֶת (yod inicial cae): esqueleto לדת,
                    # empieza en ל y por eso escapaba a la guarda de prefijos. Acotado
                    # a INF + esqueleto exacto לדת para no colisionar (Gén 38:5/38:27
                    # בְּלִדְתָּהּ «al dar a luz»).
                    or ('INF' in m.upper() and ck[:3] == 'לדת'))
        if es_yalad:
            mm = m.upper()
            plural = ('.PL' in mm or '.DU' in mm)
            if any(t in mm for t in ('WAYYIQT', 'WATIQT', 'QATAL', 'PERF', 'SEQ')):
                forma = 'dieron a luz' if plural else 'dio a luz'
            elif any(t in mm for t in ('YIQTOL', 'IMPF', 'JUS', 'COH', 'IMPV')):
                forma = 'darán a luz' if plural else 'dará a luz'
            elif 'INF' in mm:
                forma = 'dar a luz'
            elif 'PTC' in mm:
                forma = 'da a luz'
            else:
                forma = 'dio a luz'
            if es[:1].isupper():
                forma = forma[:1].upper() + forma[1:]
            return (f'verbo de parto ילד glosado «{es}» (truncado de «dar a luz») '
                    f'→ «{forma}»', ('set_es', forma, hw.get('es') or ''))
    # ── preposición עִם (H5973 «con») glosada con un homógrafo de CONTENIDO:
    #    עַם H5971 «pueblo» o עמד H5975 «parado» (עִמָּדִי «conmigo» quedaba
    #    «parado»). La morfología PREP es inequívoca: una preposición NUNCA
    #    significa eso → autofix de raíz. Cuando lleva sufijo pronominal se
    #    RECONSTRUYE «con + pronombre»: primero DESDE LA MORFOLOGÍA del sufijo
    #    (_con_pronombre); si falta la morfología (עִמָּדִי no trae PRS.*, solo
    #    prs_suffix.es «mí»), DESDE LA GLOSA del sufijo (_SUF_ES_A_CON). Se limpia
    #    el sufijo. Fusiona conmigo/contigo/consigo. Gén 24:25 «pueblo nosotros»→
    #    «con nosotros»; «su con» (3ms)→«con él»; «parado»+«mí»→«conmigo».
    if morph_root(m) == 'PREP' and (ck[:2] == 'עמ' or ck[:2] == 'את') and es:
        parts = es.split()
        w0 = parts[0].lower() if parts else ''
        # FUSIÓN conmigo/contigo: la raíz YA es «con» (válida) pero el sufijo de
        # 1ª/2ª sg NO quedó fusionado y el render sale roto («te con», «con ti»,
        # «con mí»). El español EXIGE la forma sintética: עם/את + 1ª sg → «conmigo»,
        # + 2ª sg → «contigo». Solo se dispara cuando la reconstrucción por
        # morfología es conmigo/contigo/consigo (1ª/2ª sg) y el render actual de
        # raíz+sufijo NO coincide (3ª/plural = «con él/nosotros…» ya correctos NO
        # se tocan; el prefijo «de» de מֵעִם se conserva porque se compara solo
        # raíz+sufijo, no el prefijo). Gén 26:3 «te con»→«contigo», 26:24 «con
        # ti»→«contigo».
        if w0 in ('con', 'conmigo', 'contigo', 'consigo'):
            fus = _con_pronombre(prs_morph(hw))
            if fus and fus in ('conmigo', 'contigo', 'consigo'):
                actual = combinar_es(es, prs_es(hw), m)
                if actual.lower() != fus.lower():
                    newes = fus[:1].upper() + fus[1:] if es[:1].isupper() else fus
                    return (f'preposición עִם/אֵת + sufijo 1ª/2ª sg: render «{actual}» '
                            f'→ «{newes}» (fusión conmigo/contigo)',
                            ('idiom', newes, hw.get('es') or ''))
        # Una PREP עם/את SIEMPRE significa «con». Cualquier raíz que NO sea ya una
        # forma «con» válida (con/conmigo/contigo/consigo) NI otra preposición
        # válida (respeto a lecturas «a/de/en»…) es errónea (pueblo/parado/«y»/«un»/
        # «su»…) → reconstruye «con + pronombre». «contigo»/«conmigo» ya correctos
        # NO se tocan (evita no-ops que borrarían el sufijo).
        if (w0 and w0 not in ('con', 'conmigo', 'contigo', 'consigo')
                and w0 not in _PREP_VALIDA_ES):
            full = _con_pronombre(prs_morph(hw))
            if not full:
                full = _SUF_ES_A_CON.get(prs_es(hw).strip().lower())
            if full:
                if es[:1].isupper():
                    full = full[:1].upper() + full[1:]
                if full.lower() != es.lower():   # solo si cambia algo
                    return (f'preposición עִם/אֵת «con» glosada «{es}» (raíz errónea) '
                            f'→ «{full}» (reconstruido del sufijo)',
                            ('idiom', full, hw.get('es') or ''))
                return None
            # sin sufijo pronominal en el campo suffix, pero el PRONOMBRE está
            # incrustado en la propia raíz («pueblo él», «parado nosotros»): la
            # ÚLTIMA palabra es un tónico → reconstruye «con+pron» (fusión conmigo/
            # contigo). Aplica a עם y את.
            last = parts[-1].lower()
            if len(parts) >= 2 and last in _SUF_ES_A_CON:
                newes = _SUF_ES_A_CON[last]
                if es[:1].isupper():
                    newes = newes[:1].upper() + newes[1:]
                return (f'preposición עִם/אֵת «con» glosada «{es}» (raíz errónea) → '
                        f'«{newes}»', ('set_es', newes, hw.get('es') or ''))
            # una palabra suelta claramente errónea (pueblo/parado/«y»/«un»/«su»…)
            # sobre עם puro → «con». Si la glosa es una FRASE (p.ej. «lejos de lo
            # habitado», Job 28:4) NO se toca: lectura frasal legítima, no homógrafo
            # roto. את NO entra aquí (posible marcador de objeto H853 mal etiquetado).
            if (ck[:2] == 'עמ' and len(parts) == 1
                    and w0 in (_PREP_STEM_MALO | set(_IM_HOMOGRAF_WRONG))):
                newes = 'Con' if es[:1].isupper() else 'con'
                return (f'preposición עִם «con» glosada «{es}» (raíz errónea) → '
                        f'«{newes}»', ('set_es', newes, hw.get('es') or ''))
    # ── adverbio de lugar שָׁם/שָׁמָּה (ADV) glosado «nombre»: confusión con el
    #    SUSTANTIVO שֵׁם «nombre» (no con el verbo שׂם «poner»). Un adverbio de
    #    lugar nunca es «nombre» → «allí»/«allá». Determinista por MORFOLOGÍA (ADV,
    #    autoridad del lado español) + esqueleto שם; NO depende del Strong (Gén
    #    26:25 quedó con H8034/שֵׁם mal etiquetado pero morfología ADV y contexto
    #    «edificó allí… plantó allí su tienda»). No entra en la guarda _PUT_GLOSSES
    #    porque la glosa errónea es el sustantivo, no el verbo.
    if morph_root(m) == 'ADV' and ck in ('שמ', 'שמה'):
        low = (es or '').lower().strip(' .,;:')
        if low in ('nombre', 'nombres', 'nombre de', 'un nombre'):
            reading = 'allá' if ck == 'שמה' else 'allí'
            if es[:1].isupper():
                reading = reading[:1].upper() + reading[1:]
            return (f'adverbio de lugar שָׁם/שָׁמָּה glosado «{es}» (sustantivo שֵׁם '
                    f'«nombre») → «{reading}»', ('set_es', reading, hw.get('es') or ''))
    if not es or es.lower() not in _PUT_GLOSSES:
        return None
    root = morph_root(m)
    if ck in ('שמ', 'שמה') and root == 'ADV':
        reading = 'allá' if ck == 'שמה' else 'allí'
        return (f'adverbio de lugar שָׁם/שָׁמָּה glosado «{es}» (verbo שׂם) → «{reading}»',
                ('set_es', reading, hw.get('es') or ''))
    if ck == 'שמ' and root == 'SUBS':
        return (f'sustantivo שֵׁם «nombre» glosado «{es}» (verbo שׂם) → «nombre»',
                ('set_es', 'nombre', hw.get('es') or ''))
    return None


# ── PREPOSICIÓN + SUFIJO PRONOMINAL: reconstrucción determinista del render ──
# PRINCIPIO ÚNICO: el único render correcto de una PREP con sufijo pronominal es
# «<preposición> <pronombre tónico>» (a mí, en él, de ellos, sobre nosotros, tras
# ti). El PRONOMBRE lo fija SIEMPRE la MORFOLOGÍA del sufijo (autoridad). La
# PREPOSICIÓN: si la raíz YA es una preposición válida se RESPETA (incluida la
# elección a/para de ל); si la raíz es una palabra NO preposicional (funcional
# errónea «un/y/su», artículo/clítico «el/la/lo», o el pronombre tónico pegado del
# constructo אֵלֵי/עֲלֵי leído «a mí»), la preposición se deriva del esqueleto
# hebreo. Con raíz basura sobre ל se SUPLE «a»+pronombre (a↔para es estilo tuyo,
# ajustable; el motor nunca deja «un mí»). Esto unifica: «un mí»→«a mí», «su
# ellos»→«en ellos», «a mí él»→«a él»
# (constructo), «su en»→«en ellos», «para y»→«para él», «a»→«a mí», «la ella»→
# «a ella». עם/את → «con» las maneja check_homograf (fusión conmigo/contigo).
_PREP_SKEL_ES = [
    ('אחר', 'tras'), ('אל', 'a'), ('על', 'sobre'), ('עד', 'hasta'),
    ('מן', 'de'), ('מ', 'de'), ('ב', 'en'),
]
_PREP_STEM_MALO = {'un', 'una', 'unos', 'unas', 'y', 'o', 'e', 'u',
                   'su', 'sus', 'mi', 'mis', 'tu', 'tus'}
# Artículos/clíticos que se colaron como raíz de una PREP (אֵלֶיהָ «la ella»,
# אֵלֶיךָ «lo ti»): SOLO se corrigen cuando hay sufijo pronominal (así el pronombre
# se reconstruye limpio); sin sufijo son demasiado contextuales → no se tocan.
_PREP_STEM_ART = {'el', 'la', 'lo', 'los', 'las', 'le', 'les', 'al', 'del'}
_PREP_VALIDA_ES = {'a', 'para', 'de', 'en', 'con', 'sobre', 'tras', 'hasta',
                   'hacia', 'por', 'ante', 'bajo', 'desde', 'entre', 'contra',
                   'según', 'segun'}
# Pronombres tónicos que pueden aparecer PEGADOS a la preposición en la raíz como
# ARTEFACTO del constructo (אֵלֵי/עֲלֵי → «a mí»/«sobre mí»); el real lo da el sufijo.
_ES_TONIC_SET = {'mí', 'ti', 'sí', 'él', 'ella', 'ellos', 'ellas',
                 'nosotros', 'nosotras', 'ustedes'}


def _norm_cmp(s):
    return (s or '').strip().lower().strip('¿?¡!.,;:')


def _tonico_de_sufijo(prs_m, suf_es):
    """Pronombre tónico español (mí/ti/él/ella/nosotros/ustedes/ellos/ellas) según
    la MORFOLOGÍA del sufijo PRS; si falta, cae a la GLOSA del sufijo."""
    u = (prs_m or '').upper()
    if u.startswith('PRS'):
        per = '1' if 'P1' in u else '2' if 'P2' in u else '3' if 'P3' in u else ''
        pl = ('.PL' in u or '.DU' in u or u.endswith('PL'))
        fem = ('.F.' in u or u.endswith('.F'))
        if per == '1':
            return 'nosotros' if pl else 'mí'
        if per == '2':
            return 'ustedes' if pl else 'ti'
        if per == '3':
            if pl:
                return 'ellas' if fem else 'ellos'
            return 'ella' if fem else 'él'
    return {'mí': 'mí', 'mi': 'mí', 'me': 'mí', 'ti': 'ti', 'te': 'ti',
            'él': 'él', 'ella': 'ella', 'ellos': 'ellos', 'ellas': 'ellas',
            'nosotros': 'nosotros', 'nosotras': 'nosotras', 'ustedes': 'ustedes',
            'sí': 'él'}.get((suf_es or '').strip().lower())


def _prep_es_de_esqueleto(ck):
    for pre, sp in _PREP_SKEL_ES:
        if ck.startswith(pre):
            return sp
    return None


def check_prep_pron(hw):
    """Render correcto de PREP+sufijo = «<preposición> <pronombre tónico>». El
    pronombre lo fija la MORFOLOGÍA. La preposición se RESPETA si la raíz ya es
    válida (incl. a/para de ל); si no, se deriva del esqueleto; con ל de raíz
    basura se SUPLE «a»+pronombre (a↔para es estilo tuyo). עם/את → HOMOGRAF. No
    toca frases legítimas («por causa de») ni glosas ya correctas ni «a mí» 1ª sg
    sin sufijo."""
    m = hw.get('he_morph') or ''
    if morph_root(m) != 'PREP':
        return None
    es = (hw.get('es') or '').strip()
    if not es:
        return None
    ck = consk(hw.get('he_form') or '').translate(_FINALES)
    if ck[:2] in ('עמ', 'את'):        # «con»: responsabilidad de check_homograf
        return None
    prs = hw.get('prs_suffix') or {}
    prsm = prs.get('he_morph') or ''
    prse = (prs.get('es') or '').strip()
    is_prs = prsm.upper().startswith('PRS')
    pron = _tonico_de_sufijo(prsm, prse) if is_prs else None
    if is_prs and not pron:          # sufijo pronominal irreconstruible → no arriesgar
        return None
    words = es.split()
    w0 = words[0].lower()
    lamed = (ck[:1] == 'ל')

    # ── 1) determinar la PREPOSICIÓN española objetivo ───────────────────────
    prep = None
    if w0 in _PREP_VALIDA_ES:
        # raíz YA preposicional: se respeta la elección (a/para incluidas).
        if len(words) == 1:
            prep = w0
        elif len(words) == 2 and words[1].lower() in _ES_TONIC_SET and is_prs:
            # pronombre tónico PEGADO = artefacto del constructo (אֵלֵי «a mí»);
            # el pronombre REAL lo trae el sufijo → se descarta el artefacto.
            prep = w0
        else:
            return None              # frase legítima («por causa de»…) → no tocar
    elif w0 in _PREP_STEM_MALO or (w0 in _PREP_STEM_ART and is_prs):
        if lamed:
            # ל con raíz BASURA (un/su/y/artículo): no hay preposición que respetar,
            # así que dejar «un mí» es un error puro. Se SUPLE con «a» (lectura
            # dominante de complemento indirecto). a↔para sigue siendo ESTILO tuyo:
            # ajústalo a «para» donde prefieras; el motor nunca deja la basura.
            prep = 'a'
        else:
            prep = _prep_es_de_esqueleto(ck)
            if not prep:
                return None
    else:
        return None                  # raíz no reconocible → no arriesgar

    # ── 2) construir objetivo prep + pronombre y comparar con lo actual ──────
    target = f'{prep} {pron}' if (is_prs and pron) else prep
    if es[:1].isupper():
        target = target[:1].upper() + target[1:]
    current = (f'{es} {prse}'.strip()) if prse else es
    if _norm_cmp(current) == _norm_cmp(target):
        return None
    return (f'preposición+pronombre «{current}» → «{target}» (preposición del '
            f'hebreo, pronombre de la morfología)',
            ('idiom', target, hw.get('es') or ''))


# Verbos hebreos de POSTRACIÓN/REVERENCIA que son INTRANSITIVOS en hebreo y
# PRONOMINALES en español (llevan clítico reflexivo obligatorio): al glosarlos
# como transitivos se pierde el «se/me/te/nos» (Gén 24:26 «inclinó»→«se inclinó»,
# 24:48 «incliné»→«me incliné»). El clítico DEBE concordar con la persona del
# verbo hebreo.  קדד H6915 (inclinar la cabeza), שחה H7812 (postrarse/
# prosternarse, Hishtaphel שתח), כרע H3766 (arrodillarse), שחח H7817 (abatirse).
# NO se incluye נטה H5186: es Hifil TRANSITIVO («extender/inclinar la mano, el
# oído, los cielos») y NO lleva reflexivo → queda explícitamente excluido.
_REFLEX_BOW_STRONG = {'H6915', 'H7812', 'H3766', 'H7817'}
_REFLEX_CLITICS = {'me', 'te', 'se', 'nos', 'os'}
# 2ª COMPUERTA (semántica): la glosa española debe ser uno de los verbos de
# postración PRONOMINALES en español. Se EXCLUYE «adorar/reverenciar» —son
# TRANSITIVOS: «adoró a Dios», sin reflexivo— y cualquier glosa que no sea uno de
# estos verbos (sustantivos «reverencia», glosa errónea «estar/puso», inglés sin
# traducir). Así solo se añade el reflexivo donde el español lo exige de verdad.
_REFLEX_VERB_STEMS = ('inclin', 'postr', 'prostern', 'arrodill', 'abat')
# Enclítico reflexivo YA presente sobre infinitivo (r+pron) o gerundio (ndo+pron):
# postrarse/postrarme/postrarnos, inclinándose/inclinándonos… El «(r|ndo)» previo
# evita falsos positivos con finitos que acaban en esos pronombres por conjugación
# (inclinaste = s+te, inclinamos = m+os): NO llevan r/ndo antes → no se marcan.
_REFL_ENCLIT_RE = re.compile(r'(r|ndo)(me|te|se|nos|os)$')


def _clitico_reflexivo(m):
    """Clítico reflexivo español (me/te/se/nos) según persona/número del VERBO
    hebreo. 2ª pl → «se» (español neutro/LatAm «ustedes»); ese caso se reporta,
    no se auto-corrige (posible peninsular «inclinaos/inclinéis»)."""
    per = _morph_person(m)
    pl = (_morph_number(m) == 'PL' or '.DU' in (m or ''))
    if per == '1':
        return 'nos' if pl else 'me'
    if per == '2':
        return 'se' if pl else 'te'
    return 'se'


def _reemplazar_ultimo(es, viejo, nuevo):
    """Reemplaza la última aparición (sin distinguir mayúsculas) de `viejo`."""
    i = es.lower().rfind(viejo.lower())
    if i < 0:
        return es
    return es[:i] + nuevo + es[i + len(viejo):]


def check_reflexivo(hw):
    """Añade el clítico reflexivo que falta a los verbos de postración
    pronominales (ver _REFLEX_BOW_STRONG). AUTOFIX seguro para formas finitas
    (proclítico: «se inclinó», «me incliné», «se inclinaron») e infinitivos
    (enclítico: «inclinar»→«inclinarse»). Imperativo, participio, gerundio y 2ª
    plural (posible peninsular) → sin tocar. Gated por Strong para no afectar al
    transitivo נטה H5186. Respeta si ya lleva reflexivo (suelto o enclítico)."""
    m = hw.get('he_morph') or ''
    if morph_root(m) != 'VERBO':
        return None
    st = (hw.get('strongs') or '').strip()
    if st == 'H5186':                      # natah TRANSITIVO: jamás reflexivo
        return None
    ck = consk(hw.get('he_form') or '')
    # Hishtaphel de שחה lleva infijo ת → esqueleto contiene «שתח» (específico; no
    # colisiona con שחת «destruir», que es ש-ח-ת). Resto: gated por Strong.
    if not (st in _REFLEX_BOW_STRONG or 'שתח' in ck):
        return None
    es = (hw.get('es') or '').strip()
    if not es:
        return None
    toks = es.lower().split()
    if any(t in _REFLEX_CLITICS for t in toks):
        return None                        # ya lleva clítico suelto (se/me/te…)
    head = _verb_head(es)
    if not head:
        return None
    # 2ª compuerta: solo verbos de postración PRONOMINALES (excluye adorar/
    # reverenciar transitivos, sustantivos, glosas erróneas, inglés).
    if not head.startswith(_REFLEX_VERB_STEMS):
        return None
    # ya reflexivo ENCLÍTICO (infinitivo/gerundio): inclinarse, postrarnos,
    # inclinándose, postrándonos…
    if _REFL_ENCLIT_RE.search(head):
        return None
    mm = m.upper()
    per, num = _morph_person(m), _morph_number(m)
    # Casos que requieren criterio (imperativo/participio/gerundio/2ª pl posible
    # peninsular): NO se auto-corrigen para evitar formas mal acentuadas o mezcla
    # peninsular/LatAm («inclínate», «inclinado», «inclinando», «inclinaos»).
    if ('IMPV' in mm or 'PTC' in mm
            or head.endswith(('ado', 'ido', 'ada', 'ida', 'ados', 'idos',
                              'adas', 'idas', 'ndo'))
            or (per == '2' and num == 'PL')
            or head.endswith(('áis', 'éis'))):
        return None
    cl = _clitico_reflexivo(m)
    lex = st or ck[:4]
    # INFINITIVO ESPAÑOL real (-ar/-er/-ir) → enclítico invariable «-se»
    # (inclinar→inclinarse). Requiere _INF_RE aunque la morfología hebrea sea
    # INFC/INFA: si la glosa NO es un infinitivo español (p.ej. «adoraron» bajo
    # una morfología INFA) va por la rama finita (proclítico), nunca «-se» pegado.
    if _INF_RE.match(head):
        new = _reemplazar_ultimo(es, head, head + 'se')
        if new == es:
            return None
        return (f'verbo pronominal de postración ({lex}) glosado «{es}» → '
                f'«{new}» (infinitivo enclítico)',
                ('set_es', new, hw.get('es') or ''))
    # FINITO → proclítico, respetando conjunción inicial (y/e/que/no/ni) y mayúscula
    if toks[0] in ('y', 'e', 'que', 'no', 'ni'):
        first = es.split()[0]
        resto = es[len(first):].lstrip()
        new = f'{first} {cl} {resto}'
    elif es[:1].isupper():
        new = f'{cl.capitalize()} {es[0].lower()}{es[1:]}'
    else:
        new = f'{cl} {es}'
    return (f'verbo pronominal de postración ({lex}) glosado «{es}» → '
            f'«{new}» (reflexivo {cl})', ('set_es', new, hw.get('es') or ''))


def check_conjuga(hw):
    """Formas verbales españolas INEXISTENTES (errores del pipeline) → forma
    correcta. Determinista y ACOTADO a VERBO. Extensible con _CONJUGA_FIX.
    Ej.: יצא participio «salan» (no existe) → «salen» (Gén 24:13, Éx 25:33…)."""
    if morph_root(hw.get('he_morph') or '') != 'VERBO':
        return None
    es = (hw.get('es') or '').strip()
    fix = _CONJUGA_FIX.get(es.lower())
    if not fix:
        return None
    if es[:1].isupper():
        fix = fix[:1].upper() + fix[1:]
    if fix == es:
        return None
    return (f'forma verbal inexistente «{es}» → «{fix}»', ('set_es', fix, hw.get('es') or ''))


def _es_sonido_i(palabra):
    """¿La palabra española empieza por sonido /i/? (regla y→e).
    True para «i-» y «hi-» (Isaac, hizo, hirió, índice); False para el diptongo
    «hie-» (hielo, hierba, hierro → se mantiene «y»). None si no hay palabra."""
    w = (palabra or '').strip().lower().lstrip('¿¡"«“(\'')
    if not w:
        return None
    w = w.replace('í', 'i')          # índice, íbamos… (sonido i con tilde)
    if w.startswith('hie'):          # hielo/hierba/hierro = /je/ → sigue «y»
        return False
    return w.startswith('hi') or w.startswith('i')


def _palabra_siguiente(hw, idx):
    """Primera palabra del render que sigue al prefijo `idx`: otro prefijo
    posterior no vacío o, si no hay, la glosa de la raíz."""
    pes = hw.get('prefix_es') or []
    for j in range(idx + 1, len(pes)):
        w = (pes[j] or '').strip()
        if w:
            return w
    return (hw.get('es') or '').strip()


def check_eufonia(hw):
    """Eufonía de la conjunción «y/e» (ortografía española, determinista).
    «y» → «e» ante sonido /i/ inicial (i-/hi-, salvo «hie-»): «e hizo», «e
    Israel». Y a la inversa, «e» → «y» cuando la palabra siguiente NO empieza
    por sonido i (corrige una «e» mal aplicada). Devuelve lista de
    (prefix_idx, nuevo, viejo, detalle)."""
    pes = hw.get('prefix_es') or []
    out = []
    for i, p in enumerate(pes):
        val = (p or '').strip()
        if val.lower() not in ('y', 'e'):
            continue
        nxt = _palabra_siguiente(hw, i)
        iss = _es_sonido_i(nxt)
        if iss is None:
            continue
        if iss and val.lower() == 'y':
            nuevo = 'E' if val[:1].isupper() else 'e'
            out.append((i, nuevo, val, f'conjunción «y» ante sonido i- («{nxt}») → «{nuevo}»'))
        elif (not iss) and val.lower() == 'e':
            nuevo = 'Y' if val[:1].isupper() else 'y'
            out.append((i, nuevo, val, f'conjunción «e» ante «{nxt}» (no i-) → «{nuevo}»'))
    return out


# Conjunciones de PROPÓSITO/FINAL que un vav consecutivo (wayyiqtol) NUNCA puede
# ser: el wayyiqtol es narrativo secuencial y su vav se glosa «y» (o «e» eufónico,
# que resuelve EUFONIA). «para que luchaban» (Gén 25:22) es error puro.
_VAV_PROPOSITO = {'para que', 'para', 'a fin de que', 'a fin de',
                  'para que no', 'para no'}


def check_vav_wayyiqtol(hw):
    """AUTOFIX (VAV). El prefijo CONJ (vav) de un WAYYIQTOL es el vav consecutivo
    NARRATIVO: su ÚNICA glosa correcta es «y» (o «e» eufónico, que resuelve EUFONIA).
    Cualquier otra glosa es error puro, porque el wayyiqtol NO admite subordinación
    en el propio vav: ni PROPÓSITO/FINAL («para que», «para», «a fin de que»…), ni
    CONDICIONAL/SUBORDINANTE («si», «que», «como», «hasta que»…), ni —peor— una
    corrupción de build («su», «sus», «ella a»…). El sentido subordinante que a veces
    acompaña (וַיְהִי כַּאֲשֶׁר = «y sucedió CUANDO…») lo aporta SIEMPRE el término
    siguiente (אֲשֶׁר/infinitivo con prefijo כ), nunca el vav; por eso normalizar el
    vav a «y» no pierde nada. El propósito legítimo solo cabe ante volitivo
    (cohortativo/yusivo/imperfectivo), que NO es wayyiqtol y NO se toca.
    Determinista e idempotente. Devuelve lista de (prefix_idx, viejo)."""
    m = hw.get('he_morph') or ''
    if 'WAYYIQT' not in m:
        return []
    pl = hw.get('prefix_es') or []
    pm = hw.get('prefix_morphs') or []
    if not isinstance(pl, list):
        return []
    out = []
    for i, pe in enumerate(pl):
        pmi = pm[i] if (isinstance(pm, list) and i < len(pm)) else ''
        if pmi != 'CONJ':
            continue
        g = (pe or '').strip().lower()
        # Vacío → lo maneja otra pasada (glosa ausente, no corrupción del sentido).
        # «y»/«e» ya son correctas. Cualquier OTRA glosa del vav consecutivo es error.
        if g and g not in ('y', 'e'):
            out.append((i, pe))
    return out


def _es_ki(hw):
    """El לexema כִּי (H3588): por Strong o por esqueleto consonántico 'כי'."""
    return (hw.get('strongs') == 'H3588') or (consk(hw.get('he_form') or '') == 'כי')


# Glosa DEFAULT de כי cuando quedó como basura «y». כי es polisémica
# (que/porque/cuando/pues/ciertamente…); «que» es la lectura más común y neutra.
# Como el default «a» de PREPRON, se suple y el usuario ajusta a mano el causal
# «porque» / temporal «cuando» donde el contexto lo pida.
_KI_DEFAULT = 'que'


def check_ki(hw):
    """AUTOFIX (KI). כִּי (H3588) es una CONJUNCIÓN SUBORDINANTE (que/porque/cuando/
    pues/ciertamente/sino…); JAMÁS es la copulativa «y» (esa es el waw ו). Detectar
    la «y» es determinista; el valor correcto NO (depende del contexto), así que se
    suple el DEFAULT «que» (glosa más común) y el usuario ajusta «porque»/«cuando».
    Dos correcciones:
      (a) «y» ESPURIA en el prefijo de un כי cuya grafía NO empieza por vav → se
          quita (basura del build; solo וְכִי con vav real llevaría conjunción).
      (b) el propio lexema glosado «y» → se pone «que».
    Devuelve lista de (detalle, suggest, field)."""
    if not _es_ki(hw):
        return []
    m = hw.get('he_morph') or ''
    if 'CONJ' not in m:
        return []
    out = []
    ck = consk(hw.get('he_form') or '')
    # (a) «y» espuria en prefijo (la forma no trae vav)
    if not ck.startswith('ו'):
        pl = hw.get('prefix_es') or []
        if isinstance(pl, list):
            for i, pe in enumerate(pl):
                if (pe or '').strip().lower() == 'y':
                    out.append((f"כי (H3588) con «y» espuria en el prefijo "
                                f"(la forma no trae vav) → se quita",
                                ('pfx_set', i, '', pe), None))
    # (b) lexema «y» → default «que»
    if (hw.get('es') or '').strip().lower() == 'y':
        out.append((f"כי (H3588) glosado «y» (imposible: no es la copulativa waw); "
                    f"default «{_KI_DEFAULT}» (ajusta «porque»/«cuando» por contexto)",
                    ('set_es', _KI_DEFAULT, hw.get('es')), 'es'))
    return out


def _es_pen(hw):
    """El lexema פֶּן (H6435): por Strong o por esqueleto consonántico 'פן'."""
    return (hw.get('strongs') == 'H6435') or (consk(hw.get('he_form') or '') == 'פן')


# Glosa DEFAULT de פֶּן cuando quedó como basura «y». פֶּן es una conjunción de
# APRENSIÓN/finalidad negativa (no sea que / para que no / quizá / tal vez / por si
# acaso); «no sea que» es la lectura canónica más común. Como el default de KI, se
# suple y el usuario ajusta a «quizá»/«para que no» donde el contexto lo pida
# (p.ej. Gén 26:9 → «quizá»).
_PEN_DEFAULT = 'no sea que'


def check_pen(hw):
    """AUTOFIX (PEN). פֶּן (H6435) es una CONJUNCIÓN de aprensión / finalidad negativa
    (no sea que / para que no / quizá / tal vez); JAMÁS es la copulativa «y» (esa es
    el waw ו). Igual que KI: detectar la «y» es determinista, el valor exacto depende
    del contexto → se suple el DEFAULT «no sea que» y el usuario ajusta.
    Dos correcciones (espejo de check_ki):
      (a) «y» ESPURIA en el prefijo de un פן cuya grafía NO empieza por vav → se quita.
      (b) el propio lexema glosado «y» → «no sea que».
    Devuelve lista de (detalle, suggest, field)."""
    if not _es_pen(hw):
        return []
    m = hw.get('he_morph') or ''
    if 'CONJ' not in m:
        return []
    out = []
    ck = consk(hw.get('he_form') or '')
    # (a) «y» espuria en prefijo (la forma no trae vav)
    if not ck.startswith('ו'):
        pl = hw.get('prefix_es') or []
        if isinstance(pl, list):
            for i, pe in enumerate(pl):
                if (pe or '').strip().lower() == 'y':
                    out.append((f"פן (H6435) con «y» espuria en el prefijo "
                                f"(la forma no trae vav) → se quita",
                                ('pfx_set', i, '', pe), None))
    # (b) lexema «y» → default «no sea que»
    if (hw.get('es') or '').strip().lower() == 'y':
        out.append((f"פן (H6435) glosado «y» (imposible: es conjunción de aprensión, "
                    f"no la copulativa waw); default «{_PEN_DEFAULT}» (ajusta "
                    f"«quizá»/«para que no» por contexto)",
                    ('set_es', _PEN_DEFAULT, hw.get('es')), 'es'))
    return out


# Glosas que RECURREN de forma legítima entre palabras distintas (numerales,
# medidas, fórmulas de fecha) y NO deben marcarse como contagio.
_CONTAGIO_STOP = {
    'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve', 'diez',
    'cien', 'ciento', 'mil', 'año', 'años', 'día', 'días', 'vez', 'veces',
    'mucho', 'muchos', 'mucha', 'muchas', 'todo', 'toda', 'todos', 'todas',
}


def _norm_strong(s):
    s = (s or '').strip().upper()
    mo = re.match(r'^([HG])0*(\d+)', s)
    return f'{mo.group(1)}{mo.group(2)}' if mo else s


# Raíz consonántica plegando formas finales (usa la tabla _FINALES ya definida
# arriba), para que ם≠מ / ן≠נ… no hagan ver «distinta» a la misma palabra
# (שֵׁם vs שְׁמִ = raíz שם).
def _raiz_norm(he):
    return consk(he or '').translate(_FINALES)


def _misma_raiz(a, b):
    """True si a y b comparten raíz: iguales tras normalizar finales, o una es
    prefijo consonántico de la otra (≥3 letras → triliteral con afijo). Evita
    falsos positivos de contagio entre flexiones de la MISMA palabra."""
    ra, rb = _raiz_norm(a), _raiz_norm(b)
    if not ra or not rb:
        return False
    if ra == rb:
        return True
    n = min(len(ra), len(rb))
    return n >= 3 and (ra.startswith(rb) or rb.startswith(ra))


def _contagio_finding(hw, m, es, prev):
    """Decide (detalle, suggest) para un token contagiado, o None si NO es error.

    · Si la glosa actual es una glosa **conocida-correcta** del lexema según tu
      estadística (por Strong o raíz) → no es contagio → None (se descarta).
    · **AUTOFIX** (suggest set_es) SOLO cuando el Strong/raíz VERIFICA un lexema
      correcto: preferida POR-FORMA de una palabra de contenido NOMINAL (SUBS/ADJ),
      limpia, no ambigua, con n≥MIN_N y pct≥MIN_PCT, distinta del contagiado y que
      no esté ya en el token. Verbos, multipalabra o baja confianza → REPORTE con
      candidato (el lexema/tiempo lo eliges tú). Sin estadística → REPORTE."""
    st = (hw.get('strongs') or '').strip()
    sk = consk(hw.get('he_form') or '')
    veci = prev.get('he_form')
    base = f"posible CONTAGIO: «{es}» = glosa del vecino {veci!r} (Strong/forma distintos)"
    if estilo_usuario is not None:
        if st and estilo_usuario.glosa_conocida(st, m, es):
            return None
        if not st and sk and estilo_usuario.glosa_conocida_sk(sk, m, es):
            return None
    pref = None
    if estilo_usuario is not None:
        pref = estilo_usuario.preferida(st, m) if st else None
        if not pref and sk:
            pref = estilo_usuario.preferida_sk(sk, m)
    cand = pref[0] if pref else None
    ya = _palabras_token_es(hw, con_es=False)
    if (cand and m.startswith(_GLOSAFUNC_FIX)          # NOMINAL (SUBS/ADJ)
            and ' ' not in es                           # contagio de UNA palabra
            and _glosafunc_limpia(cand)
            and cand.lower() != es.lower()
            and cand.lower() not in ya
            and (pref[1] or 0) >= _GLOSAFUNC_MIN_PCT
            and (pref[2] or 0) >= _GLOSAFUNC_MIN_N):
        return (f"{base} → «{cand}» ({pref[1]:.0f}%, n={pref[2]}) [verificado por Strong]",
                ('set_es', cand, hw.get('es') or ''))
    extra = (f'; candidato «{cand}» ({pref[1]:.0f}%, n={pref[2]})'
             if cand else '; sin lexema fiable por Strong/raíz')
    return (f"{base}{extra} → revisar el lexema de {hw.get('he_form')!r}", None)


def check_contagio(flat):
    """CONTAGIO — caza la glosa copiada del vecino en el build: un stem de CONTENIDO
    (SUBS/ADJ/VERBO) cuya `es` es IDÉNTICA a la del stem de contenido ANTERIOR pero
    con **Strong Y raíz consonántica DISTINTOS** → la glosa se contagió (47:14
    `שֶּׁבֶר` «grano» quedó «tierra», de `אֶרֶץ`; 36:6 `יֵּלֶךְ` «ir» quedó «tierra»;
    41:12 `נַעַר` «joven» quedó «siervo»). Alta precisión: exige palabra hebrea
    genuinamente distinta (`_misma_raiz` pliega formas finales y la variante con
    afijo) y descarta numerales/medidas (`_CONTAGIO_STOP`).

    MIXTO: **autofix** solo el subconjunto que el Strong/raíz VERIFICA (ver
    `_contagio_finding`) — en capítulos abiertos el `--apply` lo corrige al pasar; en
    capítulos CERRADOS el candado impide escribir y el hallazgo queda LISTADO
    (cap:verso) para corrección manual. El resto (verbos, sin Strong fiable) → REPORTE.
    Complementa a RECORRIDO (par inmediatamente adyacente). Recibe `flat` =
    [(pi, wi, hw)]. Devuelve [(pi, wi, he_form, morph, detalle, suggest)]."""
    out = []
    prev = None  # último stem de contenido "bueno" (hw)
    for (pi, wi, hw) in flat:
        m = hw.get('he_morph') or ''
        es = (hw.get('es') or '').strip()
        good = (morph_root(m) in ('SUBS', 'ADJ', 'VERBO')
                and not is_nprop_gent(m) and len(es) > 2)
        if not good:
            continue
        if prev is not None:
            pes = (prev.get('es') or '').strip()
            if (es.lower() == pes.lower()
                    and es.lower() not in _CONTAGIO_STOP
                    and _norm_strong(hw.get('strongs')) != _norm_strong(prev.get('strongs'))
                    and not _misma_raiz(hw.get('he_form'), prev.get('he_form'))):
                fnd = _contagio_finding(hw, m, es, prev)
                if fnd:
                    out.append((pi, wi, hw.get('he_form') or '', m, fnd[0], fnd[1]))
        prev = hw
    return out


def check_sintaxis(hw):
    """Chequeos sintácticos puntuales (report-only). Lista de (detalle, suggest):

    · לְ posesivo: preposición לְ (a/para) cuya glosa de RAÍZ es un posesivo
      (su/mi/tu…). El pipeline a veces arrastra la ל como posesivo prefijado;
      debe ser tónico («a mí / para él»). Verificado: ~1126 casos en el corpus
      que MORPH_MISMATCH no caza (excluye posesivos a propósito).
    · את acusativo: את (H853, marcador de objeto directo) con sufijo pronominal
      glosado como preposición «con» → confusión con אֵת (H854 «con»); debe ser
      objeto directo (lo/la/a él)."""
    out = []
    m = hw.get('he_morph') or ''
    es = (hw.get('es') or '').strip()
    head = es.split()[0].lower() if es else ''
    ck = consk(hw.get('he_form') or '')
    # M4 — לְ glosada como posesivo. PREPRON (autofix) ya reconstruye «a/para +
    #      tónico» en estos casos → solo se REPORTA el residuo que PREPRON NO arregla
    #      (evita el doble listado de un error que --apply ya corrige).
    if (morph_root(m) == 'PREP' and ck[:1] == 'ל' and head in POSSESSIVES
            and not check_prep_pron(hw)):
        out.append((f'preposición לְ glosada como posesivo {es!r}; debe ser forma '
                    f'tónica («a/para» + mí/ti/él/ellos…)', None))
    # M2 — את (H853) acusativo con sufijo glosado «con». HOMOGRAF (autofix) ya lo
    #      reconstruye «a + tónico» → solo se REPORTA el residuo que no autofixea.
    if (hw.get('strongs') or '').strip() == 'H853':
        suf = hw.get('prs_suffix') or {}
        if ((suf.get('he_morph') or (suf.get('es') or '').strip()) and head == 'con'
                and not check_homograf(hw)):
            out.append((f'את (H853, acusativo) glosado «con…»; es marcador de objeto '
                        f'directo → «lo/la/a él» (¿confusión con אֵת H854 «con»?)', None))
    return out


def check_construct(hw):
    """Estado CONSTRUCTO sin nexo genitivo (report-only). Aprendido de tus
    ediciones de Gén 23:1-11: el spider deja el constructo hebreo (SUBS/ADJ .C)
    como palabra suelta —«hijos», «pueblo», «campo», «puerta», «propiedad»—
    cuando el constructo es genitivo y en español pide «… de» («hijos de»,
    «pueblo de»…). Sugiere añadir «de».

    Conservador para evitar falsos positivos:
      · solo SUBS/ADJ con morfología .C (constructo), NO nombres propios.
      · SIN sufijo pronominal (con sufijo el genitivo ya lo da el sufijo:
        אֲדֹנִי «mi señor», נַפְשִׁי «nafshí» — no «señor de»).
      · si la glosa ya trae «de/del», o termina en preposición, no marca.
    """
    m = hw.get('he_morph') or ''
    if morph_root(m) not in ('SUBS', 'ADJ') or '.C' not in m or is_nprop_gent(m):
        return None
    suf = hw.get('prs_suffix') or {}
    if (suf.get('he_morph') or (suf.get('es') or '').strip()):
        return None
    # כֹּל/כָּל (todo/todos): constructo hebreo pero en español NO toma «de»
    # («todo árbol», «todos los hijos», no «todos de»). Excluir.
    if consk(hw.get('he_form') or '') == 'כל':
        return None
    stem = (hw.get('es') or '').strip()
    if not stem:
        return None
    low0 = stem.lower()
    # numerales cardinales en constructo: el número precede SIN «de»
    # («dos hijos», «tres días», «cien años», no «dos de»). El discriminador es
    # la glosa ES: שְׁנֵי «años» sí es genitivo, שְׁנֵי «dos» no.
    if low0 in _NUMERALS_ES:
        return None
    # glosa que es en sí una palabra funcional (posesivo/pronombre/artículo):
    # casi siempre glosa base corrupta («mi», «su») → no «mi de».
    if low0 in POSSESSIVES or low0 in _INDEF_ART or low0 in ARTICLES_ES:
        return None
    # demostrativo suelto (glosa base corrupta de עֲבוּר etc.): «ese» → no «ese de».
    if low0 in _DEMOS_ES:
        return None
    # glosa ADVERBIAL o VERBAL (glosa base equivocada sobre un token SUBS/ADJ):
    # no añadir «de» encima («todavía de» 29:7, «parecían de» 28:8). El constructo
    # se reportará por otras vías (MORPH_MISMATCH/ESTILO), pero nunca corrompemos
    # una glosa no-nominal con un «de».
    if low0 in _ADV_NO_DE or _VERBISH_RE.search(low0):
        return None
    # nombre transliterado (mayúscula inicial o apóstrofo: 'El, Nesí, Yah…):
    # no recibe «de» automático (decisión editorial).
    if stem[0].isupper() or stem.startswith("'"):
        return None
    words = low0.split()
    # glosa ya poseída («mi Dios», «su casa»): el genitivo lo da el posesivo, no «de».
    if words and words[0] in POSSESSIVES:
        return None
    if 'de' in words or 'del' in words:
        return None
    if words and words[-1] in PREP_ES_HEADS:
        return None
    # ESTILO manda: si tu glosa MÁS USADA para esta forma NO lleva «de»
    # (p.ej. sueles escribir «hijos», «días», «generaciones» sin «de»), no se
    # añade —evita el churn CONSTRUCT↔ESTILO—. Solo se añade «de» cuando tu uso
    # no lo contradice (o no hay datos de estilo).
    if _estilo_prefiere_sin_de(hw, stem):
        return None
    return (f'constructo (.C) glosado «{stem}» sin nexo genitivo; '
            f'el constructo pide «… de» → «{stem} de»', f'{stem} de')


def check_de_espuria(hw):
    """INVERSO de check_construct (autofix). Un nombre (SUBS/ADJ) que YA lleva
    SUFIJO PRONOMINAL no puede arrastrar un «de/del» final: el genitivo lo da el
    sufijo, no un nexo constructo (אִשְׁתּוֹ «su mujer», NO «su mujer de»;
    בֵּיתוֹ «su casa», NO «su casa de»). El «de» final es arrastre → se elimina.
    Determinista: solo actúa si hay sufijo pronominal real y la raíz TERMINA en
    «de»/«del» con al menos otra palabra delante (no toca «de» suelto)."""
    m = hw.get('he_morph') or ''
    if morph_root(m) not in ('SUBS', 'ADJ') or is_nprop_gent(m):
        return None
    suf = hw.get('prs_suffix') or {}
    if not (suf.get('he_morph') or (suf.get('es') or '').strip()):
        return None                       # sin sufijo → es competencia de check_construct
    if not is_pron_suffix(suf.get('he_morph') or ''):
        return None                       # he paragógico/locativo/PART: NO da genitivo
    # El poseedor debe rendirse PROCLÍTICO (su/mi/tu/nuestro…): solo entonces la «de»
    # final queda colgada al final del render («su mujer de»). Si el sufijo es un
    # pronombre TÓNICO pospuesto (לִפְנֵיהֶם «antes de ellos»), la «de» GOBIERNA al
    # pronombre y NO sobra → no se toca. Sin glosa de sufijo tampoco se arriesga.
    suf_es = (suf.get('es') or '').strip().lower()
    if suf_es not in POSSESSIVES and suf_es not in LONG_POSS:
        return None
    stem = (hw.get('es') or '').strip()
    if not stem:
        return None
    words = stem.split()
    # SOLO «NOMBRE de» (exactamente 2 palabras) con cabeza NO preposicional. Excluye
    # locuciones adverbiales/preposicionales (לִפְנֵי «antes de», אַחֲרֵי «después de»,
    # בְּתוֹךְ «en medio de»…): esas piden «… de él/ellos», la «de» gobierna al
    # pronombre y no sobra. Multi-palabra queda a REPORTE (LARGO), no se retoca.
    if len(words) != 2 or words[-1].lower() not in ('de', 'del'):
        return None
    if words[0].lower() in PREP_ES_HEADS:
        return None
    new = words[0]
    return (f'nombre con sufijo posesivo glosado «{stem}» arrastra '
            f'«{words[-1]}» espuria (el posesivo ya da el genitivo) → «{new}»',
            ('set_es', new, stem))


def _estilo_prefiere_sin_de(hw, stem):
    """True si tu glosa MÁS USADA para esta forma (por Strong o, si falta, por
    esqueleto) NO contiene «de»/«del» → prefieres el constructo sin nexo.
    Usa `preferida()` (ranking crudo, no depende de la glosa actual)."""
    if estilo_usuario is None:
        return False
    m = hw.get('he_morph') or ''
    pref = estilo_usuario.preferida(hw.get('strongs') or '', m)
    if not pref:
        sk = consk(hw.get('he_form') or '')
        pref = estilo_usuario.preferida_sk(sk, m) if sk else None
    if not pref:
        return False
    glosa, _pct, n, _amb = pref
    if not glosa or (n or 0) < 3:
        return False               # sin señal suficiente → deja que añada «de»
    g = glosa.strip().lower().split()
    return 'de' not in g and 'del' not in g


# ── Lexemas COMUNES transliterados por DECISIÓN EDITORIAL ──────────────────────
# Espejo VERIFICADO de fuentes/transliteraciones_lexemas.json. La lista maestra es
# la REFERENCIA; aquí codificamos solo las formas ABSOLUTAS deterministas por número
# para que el motor SUPLA la transliteración que el motor fonético NO cubre (estos
# lexemas son SUBS/ADJ comunes, no NPROP/GENT → quedaban fuera de translit_nombres).
# 'sg'/'pl' = forma absoluta · 'trad' = glosas-traducción que autorizamos convertir.
_LEXEMA_TRANSLIT = {
    'H1471': {                       # גוי  goy / goyim (nación)
        'root': 'גוי', 'gate': ('SUBS',),
        'sg': 'Goy', 'pl': 'Goyim',
        'trad': {'nación', 'nacion', 'naciones', 'gente', 'gentes',
                 'pueblo', 'pueblos', 'gentil', 'gentiles'},
    },
    'H430': {                        # אלהים  'Elohim (apelativo divino; lista maestra)
        'root': 'אלה', 'gate': ('SUBS',),
        'sg': "'Elohim", 'pl': "'Elohim",
        # SOLO «dios» (singular, Dios verdadero) → 'Elohim (esa forma exacta). El
        # plural pagano «dioses» (dioses ajenos, 35:2/35:4) y el CONSTRUCTO «dios de»
        # (grafía 'Elohei, decisión editorial) quedan FUERA → los lista MORPH_MISMATCH.
        'trad': {'dios'},
    },
    'H7656': {                       # שִׁבְעָה  n.pr. del pozo (Gén 26:33), no el numeral
        'root': 'שבע', 'gate': ('ADJ', 'SUBS'),
        'sg': "Shiv'áh", 'pl': "Shiv'áh",
        'trad': {'seba', 'sheba', 'siba', 'siva'},
    },
    'H1288': {                       # ברוך  participio QAL (Gén 26:29): transliterar, no «amparado»
        'root': 'ברכ', 'gate': ('VERBO',),
        'need': 'PTCP',
        'sg': 'Beruj', 'pl': 'Berujim',
        'trad': {'amparado', 'amparado de', 'bendito', 'bendito de', 'bendecido'},
        'keep_de': True,
    },
    'H1293': {                       # ברכה  sustantivo (Gén 27:12): Berajáh, no «amparo»/«bendición»
        'root': 'ברכה', 'gate': ('SUBS',),
        'sg': 'Berajáh', 'pl': 'Berajot',
        'trad': {'amparo', 'bendición', 'bendicion', 'bendiciones',
                 'bendición de', 'bendiciones de'},
    },
    'H7045': {                       # קללה  sustantivo (Gén 27:12): Qelaláh, no «desamparo»/«maldición»
        'root': 'קללה', 'gate': ('SUBS',),
        'sg': 'Qelaláh', 'pl': 'Qelalot',
        'trad': {'desamparo', 'maldición', 'maldicion', 'maldiciones'},
    },
}


_FINALS_TO_MEDIAL = str.maketrans({'ך': 'כ', 'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ'})


def _skel_has_root(sk, root):
    """Raíz como subsecuencia de la grafía (kaf final plegado; matres ו/י en ברוך)."""
    root = (root or '').translate(_FINALS_TO_MEDIAL)
    if not root:
        return False
    i = 0
    for ch in sk:
        if i < len(root) and ch == root[i]:
            i += 1
    return i == len(root)


def check_translit_lexema(hw):
    """AUTOFIX (TRANSLIT). Suple la transliteración de un LEXEMA COMÚN listado en
    _LEXEMA_TRANSLIT (espejo de transliteraciones_lexemas.json) cuando el motor
    fonético no lo cubre (por ser SUBS/ADJ, no NPROP/GENT). Determinista y estrecho:
    exige Strong exacto (autoridad) + raíz consonántica, FORMA ABSOLUTA (salta
    constructo .C, cuya grafía distinta —p.ej. «Goyei»— y se deja a mano/reporte) y
    que la glosa actual sea una TRADUCCIÓN conocida. Nunca toca una translit ya puesta
    ni glosas fuera del set autorizado."""
    es = (hw.get('es') or '').strip()
    he = hw.get('he_form') or ''
    sk = consk(he).translate(_FINALS_TO_MEDIAL)
    # Artefacto RV «Beerseba» pegado al segundo eslabón de באר שבע (Gén 26:33).
    if es.lower() == 'beerseba' and sk.startswith('שבע'):
        return ('topónimo באר שבע: «beerseba» en el segundo eslabón → «Shéva»',
                ('set_es', 'Shéva', hw.get('es') or ''))
    st = (hw.get('strongs') or '').strip()
    spec = _LEXEMA_TRANSLIT.get(st)
    if not spec:
        return None
    m = hw.get('he_morph') or ''
    if morph_root(m) not in spec['gate']:
        return None
    need = spec.get('need')
    if need and need not in m:
        return None
    if '.C' in m:                     # constructo: grafía distinta → no autofix
        return None
    if not _skel_has_root(sk, spec['root']):
        return None
    if not es:
        return None
    low = es.lower().strip("'")
    if low in (spec['sg'].lower().strip("'"), spec['pl'].lower().strip("'")):
        return None
    if spec.get('keep_de') and low.endswith(' de'):
        low_core = low[:-3].strip()
        if low_core in (spec['sg'].lower().strip("'"), spec['pl'].lower().strip("'")):
            return None
        if low_core not in spec['trad'] and low not in spec['trad']:
            return None
    elif low not in spec['trad']:
        return None
    target = spec['pl'] if ('.PL' in m or '.DU' in m) else spec['sg']
    if spec.get('keep_de') and es.lower().rstrip().endswith(' de') and not target.lower().endswith(' de'):
        target = target + ' de'
    return (f'lexema común {st} transliterable (lista maestra) «{es}» → «{target}»',
            ('set_es', target, hw.get('es') or ''))


# Español de ברך (verbo) que debe ceder a transliteración fonética (rojo Gén 27).
_BARAK_VERB_TRAD = {
    'amparar', 'amparó', 'amparé', 'ampare', 'amparen', 'amparado', 'amparado de',
    'ampararlos', 'ampararé', 'amparados',
    'bendecir', 'bendijo', 'bendije', 'bendiga', 'bendigas', 'bendigan',
    'bendice', 'bendíceme', 'bendito', 'bendito de', 'benditos', 'bendecido',
    'bendecirá', 'bendeciré', 'bendeciré', 'bendijeron',
}
_BARAK_CLITIC = {'me', 'te', 'le', 'lo', 'la', 'les', 'los', 'nos', 'os', 'se'}


def _translit_espanol(he_form: str) -> str:
    """Capa española del motor fonético (visor/translit_nombres). Lazy import.
    Quita te'amim antes: el acento editorial no debe depender del cantilar."""
    try:
        from translit_nombres import transliterar, TEAMIM_LO, TEAMIM_HI  # type: ignore
    except ImportError:
        _visor = Path(__file__).resolve().parents[2] / 'visor'
        if str(_visor) not in sys.path:
            sys.path.insert(0, str(_visor))
        from translit_nombres import transliterar, TEAMIM_LO, TEAMIM_HI  # type: ignore
    clean = ''.join(
        ch for ch in (he_form or '')
        if not (TEAMIM_LO <= ord(ch) <= TEAMIM_HI)
    )
    return (transliterar(clean) or {}).get('espanol') or ''


def _barak_verb_core(es: str) -> str | None:
    """Núcleo léxico bend*/ampar* de la glosa (ignora clítico proclítico)."""
    toks = (es or '').lower().strip('¿?¡!').split()
    if not toks:
        return None
    if len(toks) == 1:
        core = toks[0]
    elif len(toks) == 2 and toks[0] in _BARAK_CLITIC:
        core = toks[1]
    elif len(toks) == 2 and toks[1] in _BARAK_CLITIC:
        core = toks[0]
    else:
        return None
    core = core.strip('¿?¡!')
    if core in _BARAK_VERB_TRAD:
        return core
    if any(core.startswith(p) for p in ('bendic', 'bendij', 'bendec', 'bendig', 'ampar')):
        return core
    return None


def check_translit_barak_verb(hw):
    """AUTOFIX (TRANSLIT). Verbo ברך (PIEL/QAL finito u objeto clítico) glosado
    en español «bendecir/amparar…» → transliteración fonética por forma
    (תְּבָֽרֶכְךָ → Tevarejjá). Complementa H1288 (solo participio → Beruj).
    No toca el sustantivo H1293 (Berajáh) ni rodillas H1290."""
    m = hw.get('he_morph') or ''
    if morph_root(m) != 'VERBO':
        return None
    st = (hw.get('strongs') or '').strip()
    if st in ('H1290', 'H1293'):
        return None
    if st == 'H1288' and 'PTCP' in m:
        return None                      # ya lo cubre _LEXEMA_TRANSLIT → Beruj
    if 'PTCP' in m:
        # participio sin Strong: no fonetizar (Beruj lo fija la tabla H1288)
        return None
    # INFINITIVO constructo suelto («bendecir») también es decisión editorial
    # puntual; el rojo del visor lo aplica el motor de nombres. Aquí solo finitos
    # e imperativos con/sin clítico objeto.
    if 'INFC' in m or 'INFA' in m:
        return None
    he = hw.get('he_form') or ''
    sk = consk(he).translate(_FINALS_TO_MEDIAL)
    if not (_skel_has_root(sk, 'ברכ') or _skel_has_root(sk, 'ברך')):
        return None
    es = (hw.get('es') or '').strip()
    ps = prs_es(hw).strip()
    core = _barak_verb_core(es)
    if not core:
        return None
    fused = he + (prs_he(hw) or '')
    tr = _translit_espanol(fused)
    if not tr:
        return None
    # ya transliterado: misma forma o mayúscula no-española
    if es == tr:
        if not ps:
            return None
        return (f'ברך ya transliterado «{es}»; sufijo {ps!r} residual → limpiar',
                ('idiom', tr, es))
    if es and es[0].isupper() and not _barak_verb_core(es):
        if not ps:
            return None
        return (f'ברך ya transliterado «{es}»; sufijo {ps!r} residual → limpiar',
                ('idiom', tr if tr else es, es))
    if ps:
        return (f'verbo ברך «{combinar_es(es, ps, m)}» → translit «{tr}»',
                ('idiom', tr, es))
    return (f'verbo ברך «{es}» → translit «{tr}»',
            ('set_es', tr, es))


# Sustantivos ברכה/קללה con sufijo (constructo): tabla absoluta no aplica (.C).
# La grafía la da el motor fonético visor/translit_nombres.py (capa «espanol»).
# Apelativos divinos (H430 'Elohim / 'Elohejá…): NO van aquí — absoluto lo
# cubre _LEXEMA_TRANSLIT; constructo+sufijo lo aplica el motor de nombres desde
# el hebreo (rojo del visor / translit_nombres), no un autofix paralelo.
_BERAJA_QELALA = {
    'H1293': {'roots': ('ברכה', 'ברכ'), 'trad': {
        'amparo', 'bendición', 'bendicion', 'bendiciones', 'tu bendición',
        'mi bendición', 'su bendición', 'bendición de',
    }},
    'H7045': {'roots': ('קללה', 'קלל'), 'trad': {
        'desamparo', 'maldición', 'maldicion', 'maldiciones',
        'tu maldición', 'mi maldición', 'su maldición',
    }},
}


def check_translit_beraja_qelala_suf(hw):
    """AUTOFIX (TRANSLIT). ברכה/קללה CONSTRUCTO+sufijo (Gén 27:13 קִלְלָתְךָ)
    glosado en español → fonética (Qillatjá). Absolutos los cubre la tabla."""
    m = hw.get('he_morph') or ''
    if morph_root(m) != 'SUBS':
        return None
    if not is_pron_suffix(prs_morph(hw)):
        return None
    st = (hw.get('strongs') or '').strip()
    he = hw.get('he_form') or ''
    sk = consk(he).translate(_FINALS_TO_MEDIAL)
    spec = _BERAJA_QELALA.get(st) if st else None
    if not spec:
        # sin Strong: discriminar por esqueleto
        if _skel_has_root(sk, 'קלל'):
            spec = _BERAJA_QELALA['H7045']
        elif _skel_has_root(sk, 'ברכ'):
            spec = _BERAJA_QELALA['H1293']
        else:
            return None
    elif not any(_skel_has_root(sk, r) for r in spec['roots']):
        return None
    es = (hw.get('es') or '').strip()
    ps = prs_es(hw).strip()
    low = es.lower()
    # «tu maldición» en raíz, o «maldición»+sufijo posesivo
    ok = low in spec['trad']
    if not ok and ps:
        fused_low = combinar_es(es, ps, m).lower()
        ok = fused_low in spec['trad'] or low in {
            t.split()[-1] for t in spec['trad'] if ' ' in t
        } or low in {'maldición', 'maldicion', 'desamparo',
                     'bendición', 'bendicion', 'amparo'}
    if not ok:
        return None
    fused = he + (prs_he(hw) or '')
    tr = _translit_espanol(fused)
    if not tr:
        return None
    if es == tr and not ps:
        return None
    if ps:
        return (f'ברכה/קללה+suf «{combinar_es(es, ps, m)}» → «{tr}»',
                ('idiom', tr, es))
    return (f'ברכה/קללה+suf «{es}» → «{tr}»',
            ('set_es', tr, es))


def check_translit(hw):
    m = hw.get('he_morph') or ''
    if not is_nprop_gent(m):
        return None
    es = (hw.get('es') or '').strip()
    if not es:
        return 'NPROP/GENT sin glosa'
    if EN_PLACEHOLDER.search(es):
        return 'NPROP/GENT con [EN:]'
    if HEB_LETTER.search(es):
        return 'NPROP/GENT con hebreo'
    if es[0].islower() and es[0].isalpha():
        # AUTOFIX SOLO de la mayúscula (misma palabra, solo casing): un nombre
        # propio/gentilicio en minúscula es error gramatical objetivo. Se exige
        # UNA sola palabra alfabética para no dejar a medias topónimos compuestos
        # («mar rojo»→«Mar Rojo», que necesita criterio) → esos van a reporte.
        cap = es[0].upper() + es[1:]
        if ' ' not in es and es.replace('-', '').replace("'", '').isalpha():
            return (f'NPROP/GENT en minúscula ({es!r}) → {cap!r}',
                    ('set_es', cap, hw.get('es') or ''))
        return f'NPROP/GENT en minúscula ({es!r})'
    return None


def check_recorrido_nprop(hw, is_first, glob_prot, protected, vocab):
    es = (hw.get('es') or '').strip()
    m = hw.get('he_morph') or ''
    if not es or is_nprop_gent(m) or protected or is_first:
        return None
    st = (hw.get('strongs') or '').strip()
    if st and st in glob_prot:
        return None
    if "'" in es or '`' in es or 'ʿ' in es or 'ʾ' in es:
        return None
    if re.search(r'-[A-ZÁÉÍÓÚÑ]', es):
        return None
    if not (len(es) >= 3 and es[0].isupper() and any(c.islower() for c in es[1:])):
        return None
    if es in vocab or es.lower() in ('dios', 'señor', 'señora', 'yahveh'):
        return None
    return f'glosa parece NPROP pero morf={m}'


def check_peninsular(hw):
    """Devuelve lista de (field, idx, old, new) con formas peninsulares."""
    out = []
    es = hw.get('es') or ''
    if es.strip():
        n = to_latam_neutral(es)
        if n.strip() != es.strip():
            out.append(('es', None, es, n))
    for i, pe in enumerate(prefix_es_list(hw)):
        if pe.strip():
            n = to_latam_neutral(pe)
            if n.strip() != pe.strip():
                out.append(('prefix', i, pe, n))
    se = prs_es(hw)
    if se.strip():
        n = to_latam_neutral(se)
        if n.strip() != se.strip():
            out.append(('suf', None, se, n))
    return out


def check_yhwh(hw):
    if not is_tetra(hw):
        return None
    es = (hw.get('es') or '').strip()
    exp = tetragrammaton_es(hw.get('he_form'), 'Hashem')
    if es in ('Hashem', "'Elohim", 'Adonai'):
        if es != exp:
            return f'YHWH glosado {es!r}; por vocalización esperaría {exp!r}'
        return None
    if not es:
        return 'YHWH sin glosa'
    return f'YHWH glosado {es!r} (no es Adonai/\'Elohim/Hashem)'


# ── Concordancia de morfología verbal (tiempo/persona/número) ───────────────
# Principio: la glosa española debe respetar la morfología hebrea del verbo
# (pasado/presente/futuro, persona, número). Report-only, alta precisión.
_CLITICOS = {'se', 'me', 'te', 'nos', 'os', 'le', 'les', 'lo', 'la', 'los',
             'las', 'y', 'o', 'que', 'no', 'ni', 'a', 'de', 'en', 'ya', 'les'}
_INF_RE = re.compile(r'^[a-záéíóúñ]{3,}(ar|er|ir)$')
_VOCALES = set('aeiouáéíóú')
# Sufijos derivativos NOMINALES inequívocos: si un INFINITIVO hebreo (INFA/INFC)
# quedó glosado con una palabra que termina así, su glosa base se corrompió a un
# SUSTANTIVO derivado en vez del verbo (שקה INFC «abrevadero» en vez de «abrevar»,
# Gén 24:19). Acotado a sufijos que NO colisionan con formas verbales para no
# marcar infinitivos válidos ni el uso legítimo INF→verbo finito (report-only).
_INF_NOUN_SUF = ('dero', 'dera', 'ero', 'era', 'miento', 'ción', 'cion',
                 'sión', 'sion', 'dad', 'tad', 'eza', 'ura', 'aje', 'anza',
                 'encia', 'ancia', 'dumbre', 'ío')
# marcador plural inequívoco al final del verbo
_PL_MARK_RE = re.compile(r'(mos|áis|éis|ís)$')
# 1ª sg pretérito (acentuada) / 3ª sg pretérito (acentuada)
_P1SG_ACC_RE = re.compile(r'(é|í)$')
_P3SG_ACC_RE = re.compile(r'(ó|ió)$')
# futuro simple español, formas INEQUÍVOCAS (3ª/2ª persona): «r» + desinencia
# tónica -á/-ás/-án (levantará, dirá, pondrá, enviarás, habitarán). NO incluye
# -é/-éis: el pretérito 1ª sg de raíces en «r» también acaba en «-ré» (liberé,
# adoré) y daría falsos positivos. Ningún pretérito acaba en «-rá/-rás/-rán».
_FUT_RE = re.compile(r'r(á|ás|án)$')

# pretérito indefinido español, formas INEQUÍVOCAS: 3ª sg tónica -ó/-ió y plural
# -aron/-ieron/-eron (habló, comió, hablaron, dijeron). NO incluye el imperfecto
# -aba/-ía (lectura habitual válida del yiqtol) ni el futuro -rá (ya cubierto por
# _FUT_RE): sirve para marcar un IMPF/yiqtol renderizado como pasado puntual.
_PRET_IND_RE = re.compile(r'(ó|ió|aron|ieron|eron)$')


def _morph_person(m):
    for p in ('P1', 'P2', 'P3'):
        if p in (m or ''):
            return p[1]
    return None


def _morph_number(m):
    mm = m or ''
    if '.PL' in mm or mm.endswith('PL'):
        return 'PL'
    if '.SG' in mm or mm.endswith('SG'):
        return 'SG'
    return None


def _is_finite_verb(m):
    mm = m or ''
    if not mm.startswith('VERBO'):
        return False
    if any(t in mm for t in ('INFC', 'INFA', 'PTCA', 'PTCP', 'PTC')):
        return False
    return any(t in mm for t in ('QATAL', 'YIQTOL', 'IMPF', 'WAYYIQT', 'WATIQT',
                                 'SEQ', 'PERF', 'JUSS', 'COHORT', 'IMPV'))


def _is_infinitive_morph(m):
    mm = m or ''
    return mm.startswith('VERBO') and ('INFC' in mm or 'INFA' in mm)


def _verb_head(es):
    """Último token 'verbal' de la glosa, quitando clíticos (se levantó→levantó)."""
    toks = [t for t in re.split(r'\s+', (es or '').strip().lower()) if t]
    toks = [t.strip('¿?¡!.,;:«»""\'()') for t in toks]
    toks = [t for t in toks if t and t not in _CLITICOS]
    return toks[-1] if toks else ''


# pronombres enclíticos que pueden ir PEGADOS a un infinitivo baked ("beberle",
# "bajarla", "dárselo"): se quitan para revelar el infinitivo subyacente y así
# cazar el desajuste aunque el objeto no esté en el sufijo (recorrido/baked).
_ENCLIT_SUF = ('selos', 'selas', 'noslo', 'nosla', 'melo', 'mela', 'telo',
               'tela', 'selo', 'sela', 'nos', 'les', 'los', 'las', 'le', 'lo',
               'la', 'me', 'te', 'se', 'os')


def _quitar_enclitics(tok):
    t = tok
    for _ in range(2):
        for c in _ENCLIT_SUF:
            if len(t) > len(c) + 2 and t.endswith(c):
                t = t[:-len(c)]
                break
        else:
            break
    return t


# pretérito irregular (3ª persona SG/PL) de los verbos frecuentes en el corpus,
# para SUGERIR la forma finita correcta en el reporte (no se auto-aplica).
_IRREG_PRET = {
    'ir': ('fue', 'fueron'), 'ser': ('fue', 'fueron'),
    'hacer': ('hizo', 'hicieron'), 'decir': ('dijo', 'dijeron'),
    'dar': ('dio', 'dieron'), 'ver': ('vio', 'vieron'),
    'venir': ('vino', 'vinieron'), 'tener': ('tuvo', 'tuvieron'),
    'estar': ('estuvo', 'estuvieron'), 'andar': ('anduvo', 'anduvieron'),
    'poder': ('pudo', 'pudieron'), 'poner': ('puso', 'pusieron'),
    'saber': ('supo', 'supieron'), 'querer': ('quiso', 'quisieron'),
    'traer': ('trajo', 'trajeron'), 'caber': ('cupo', 'cupieron'),
    'caer': ('cayó', 'cayeron'), 'oír': ('oyó', 'oyeron'), 'oir': ('oyó', 'oyeron'),
    'leer': ('leyó', 'leyeron'), 'creer': ('creyó', 'creyeron'),
    'morir': ('murió', 'murieron'), 'dormir': ('durmió', 'durmieron'),
    'pedir': ('pidió', 'pidieron'), 'sentir': ('sintió', 'sintieron'),
    'seguir': ('siguió', 'siguieron'), 'servir': ('sirvió', 'sirvieron'),
    'mentir': ('mintió', 'mintieron'), 'vestir': ('vistió', 'vistieron'),
    'medir': ('midió', 'midieron'), 'repetir': ('repitió', 'repitieron'),
    'reír': ('rió', 'rieron'), 'preferir': ('prefirió', 'prefirieron'),
    'haber': ('hubo', 'hubieron'),
}


def _tiempo_autofix(hw):
    """Devuelve la forma finita (pretérito 3ª pers.) SOLO en el subconjunto SEGURO
    para auto-aplicar; None en cualquier caso dudoso (→ queda en reporte):
      · verbo QAL (evita Hifil/Hofal/Piel… causativos: «beber»→«dar de beber»);
      · pretérito narrativo/perfecto (WAYYIQT/WATIQT/QATAL, no SEQ), 3ª persona;
      · glosa = UN infinitivo, SIN enclítico ni reflexivo (no perder «se»/objeto);
      · verbo -ar regular, irregular TABULADO, o -er/-ir REGULAR (no stem-changer:
        se excluyen tallos vocálicos y los -ir que elevan la vocal e/o)."""
    m = hw.get('he_morph') or ''
    if not _is_finite_verb(m) or 'QAL' not in m:
        return None
    if 'SEQ' in m or not any(t in m for t in ('WAYYIQT', 'WATIQT', 'QATAL')):
        return None
    if _morph_person(m) != '3':
        return None
    num = _morph_number(m)
    if not num:
        return None
    toks = (hw.get('es') or '').strip().split()
    if len(toks) != 1:
        return None
    tok = toks[0].lower()
    if _quitar_enclitics(tok) != tok or tok.endswith('se'):
        return None
    if not _INF_RE.match(tok):
        return None
    if tok in _IRREG_PRET or tok.endswith('ar'):
        return _pret_3(tok, num)
    # -er/-ir REGULARES (stem+ió/ieron): seguro para autofix. Se excluyen los
    # que NO son regulares para no inventar formas:
    #   · tallo acabado en VOCAL → forma en -y- (leer→leyó, huir→huyó, caer→cayó):
    #     van tabulados o a reporte;
    #   · -ir con última vocal del tallo e/o → verbo que ELEVA la vocal en pretérito
    #     (pedir→pidió, dormir→durmió, sentir→sintió): irregular → reporte.
    if tok.endswith(('er', 'ir')):
        stem = tok[:-2]
        if not stem or stem[-1] in _VOCALES:
            return None
        if tok.endswith('ir'):
            vs = [c for c in stem if c in _VOCALES]
            if vs and vs[-1] in 'eoéó':
                return None
        return _pret_3(tok, num)
    return None


def check_tiempo_finito(hw):
    """AUTOFIX del subconjunto SEGURO de «verbo finito glosado como infinitivo»
    (ver _tiempo_autofix): conjuga el infinitivo al pretérito de 3ª persona."""
    nueva = _tiempo_autofix(hw)
    if not nueva:
        return None
    es = (hw.get('es') or '').strip()
    if nueva == es:
        return None
    return (f'verbo finito ({hw.get("he_morph")}) glosado como infinitivo '
            f'«{es}» → «{nueva}»', ('set_es', nueva, hw.get('es') or ''))


def _pret_3(inf, num):
    """Pretérito 3ª persona (num=SG/PL) de un infinitivo. None si no es fiable."""
    i = 0 if num == 'SG' else 1
    if inf in _IRREG_PRET:
        return _IRREG_PRET[inf][i]
    if inf.endswith('ducir'):
        return inf[:-5] + 'duj' + ('o' if num == 'SG' else 'eron')
    if inf.endswith('uir') and not inf.endswith(('guir', 'quir')):
        return inf[:-2] + ('yó' if num == 'SG' else 'yeron')
    if len(inf) < 3:
        return None
    stem, term = inf[:-2], inf[-2:]
    if term == 'ar':
        return stem + ('ó' if num == 'SG' else 'aron')
    if term in ('er', 'ir'):
        return stem + ('ió' if num == 'SG' else 'ieron')
    return None


# Participio pasado REGULAR de una sola palabra (masc sg): «cegado», «llenado»,
# «tocado». Excluye acentuados/irregulares (dicho/hecho/puesto/visto…) que NO
# terminan en -ado/-ido, y palabras cortas. Min 6 letras (≥3 + «ado/ido»).
_PART_RE = re.compile(r'^[a-záéíóúñ]{3,}(ad|id)o$')


def _part_pret(part, per, num):
    """Pretérito indicativo a partir de un PARTICIPIO regular, para las personas
    SEGURAS (3ª sg/pl reutilizando _pret_3; 1ª pl regular sin cambio ortográfico).
    Devuelve None en el resto (1ª/2ª sg: -é/-aste tienen cambios c→qu/g→gu/z→c que
    no vale la pena arriesgar en un reporte)."""
    if part.endswith('ado'):
        root, cls = part[:-3], 'ar'
    elif part.endswith('ido'):
        root, cls = part[:-3], 'er'   # er/ir comparten pretérito (-ió/-ieron/-imos)
    else:
        return None
    if per == '3':
        return _pret_3(root + cls, num)
    if per == '1' and num == 'PL':
        return root + ('amos' if cls == 'ar' else 'imos')
    return None


# ── GLOSAFUNC · lexema de contenido glosado como palabra funcional ──────────
# Palabras FUNCIONALES puras (clase cerrada) que NUNCA son la glosa RAÍZ de un
# lexema de contenido. Se excluyen a propósito «un/una/uno» (numeral H259),
# «a/con» (pueden formar locución prepositiva legítima) y «todo/no» (contenido/
# adverbio). Un SUBS/ADJ/VERBO glosado con una de estas = corrupción del pipeline
# de construcción (se perdió la palabra de contenido y quedó una conjunción/
# artículo/preposición/clítico arrastrado del alineamiento RVR).
_GLOSA_FUNC = {
    'y', 'e', 'o', 'u', 'ni', 'que',
    'el', 'la', 'los', 'las', 'lo',
    'de', 'del', 'al', 'en', 'por', 'para', 'sin', 'sobre', 'tras',
    'ante', 'bajo', 'contra', 'desde', 'entre', 'hacia', 'hasta', 'según',
    'me', 'te', 'se', 'nos', 'os', 'le', 'les',
    'mi', 'mis', 'tu', 'tus', 'su', 'sus', 'si',
}
_GLOSAFUNC_CONTENT = ('SUBS', 'ADJ', 'VERBO')   # lexemas de contenido detectables
_GLOSAFUNC_FIX = ('SUBS', 'ADJ')                # restauración AUTOFIX: solo NOMINAL
_GLOSAFUNC_MIN_N = 6
_GLOSAFUNC_MIN_PCT = 50.0
_GF_OK = set("abcdefghijklmnopqrstuvwxyzáéíóúñü'")


def _glosafunc_limpia(w):
    """La restauración candidata debe ser UNA palabra de contenido limpia: un
    solo token alfabético (≥2), no funcional. Descarta multi-palabra («casa de»,
    «su nombre», «el rostro»: llevan función embebida → a reporte, para no romper
    el render con el prefijo/sufijo del token)."""
    w = (w or '').strip()
    return bool(w and ' ' not in w and len(w) >= 2
                and w.lower() not in _GLOSA_FUNC
                and all(c in _GF_OK for c in w.lower()))


def _palabras_token_es(hw, con_es=True, con_pref=True, con_suf=True):
    """Conjunto de palabras españolas ya presentes en el token (raíz/prefijo/
    sufijo). Sirve para NO restaurar una glosa que YA está en otra ranura y
    generaría un duplicado en el render (p.ej. el sustantivo se filtró al prefijo:
    prefix=['años'] + raíz «que» → restaurar «años» daría «años años»)."""
    ws = set()
    if con_es:
        ws.update((hw.get('es') or '').lower().split())
    if con_pref:
        for w in (hw.get('prefix_es') or []):
            ws.update((w or '').lower().split())
    if con_suf:
        ws.update(((hw.get('prs_suffix') or {}).get('es') or '').lower().split())
    return ws


def check_glosafunc(hw):
    """Lexema de CONTENIDO (SUBS/ADJ/VERBO) cuya glosa RAÍZ es una palabra
    FUNCIONAL pura (y/de/el/que/su…). Es una CORRUPCIÓN objetiva (un sustantivo/
    verbo no puede ser «y»), no una elección de estilo. ESTILO se abstenía aquí
    porque el lexema suele ser «ambiguo» (mujer/esposa…) → la corrupción se colaba
    en SILENCIO; este es el hueco de eficiencia principal del corpus.

    Se DETECTA siempre (reporte). Se AUTOFIXea SOLO el subconjunto SEGURO: cuando
    la glosa preferida POR-FORMA (tu estadística, que ya desambigua SG/PL/constructo:
    H802.SG.C→«mujer», no «mujeres»/«tabernáculo») es UNA palabra de contenido
    limpia, con n≥6 y pct≥50 y morfología NOMINAL (SUBS/ADJ). Verbos y casos de
    baja confianza → reporte con candidato (el tiempo/persona o el sinónimo los
    eliges tú). Respeta candado + barrera (solo toca `es`) e idempotente (tras
    restaurar, la glosa ya no es funcional)."""
    if estilo_usuario is None:
        return None
    m = hw.get('he_morph') or ''
    if not m.startswith(_GLOSAFUNC_CONTENT):
        return None
    es = (hw.get('es') or '').strip()
    if not es or ' ' in es or es.lower() not in _GLOSA_FUNC:
        return None
    st = (hw.get('strongs') or '').strip()
    sk = consk(hw.get('he_form') or '')
    # ¿es una glosa que SÍ usas para este lexema? (numeral «un», prep-sustantivo…)
    if st and estilo_usuario.glosa_conocida(st, m, es):
        return None
    if not st and sk and estilo_usuario.glosa_conocida_sk(sk, m, es):
        return None
    pref = estilo_usuario.preferida(st, m) if st else None
    if not pref and sk:
        pref = estilo_usuario.preferida_sk(sk, m)
    cand = pref[0] if pref else None
    # el sustantivo NO debe estar YA en el prefijo/sufijo (evita «años años» cuando
    # el sustantivo se filtró al prefijo y la raíz quedó funcional) → si ya está, a
    # reporte (es otra corrupción: raíz funcional + sustantivo desplazado).
    ya = _palabras_token_es(hw, con_es=False)
    if (cand and cand.lower() not in ya and m.startswith(_GLOSAFUNC_FIX)
            and _glosafunc_limpia(cand) and (pref[1] or 0) >= _GLOSAFUNC_MIN_PCT
            and (pref[2] or 0) >= _GLOSAFUNC_MIN_N):
        return (f'lexema de contenido ({m}) glosado como palabra funcional «{es}» '
                f'(corrupción) → «{cand}» ({pref[1]:.0f}%, n={pref[2]})',
                ('set_es', cand, hw.get('es') or ''))
    extra = (f'; candidato «{cand}» ({pref[1]:.0f}%, n={pref[2]})'
             if cand else '; sin candidato fiable')
    return (f'lexema de contenido ({m}) glosado como palabra funcional «{es}» '
            f'(corrupción){extra} — revisar', None)


def check_suf_func(hw):
    """GEMELO de check_glosafunc en el SUFIJO: un sufijo POSESIVO (PRS.*) sobre un
    SUBS/ADJ glosado como palabra funcional NO posesiva (y/de/el/si/en…) es una
    corrupción del build (אִמּוֹ «madre y» en vez de «su madre», Gén 27:13). El
    posesivo lo fija SIEMPRE la MORFOLOGÍA del sufijo (autoridad), concordando con
    el sustantivo poseído (género/número) vía spanish_poss → DETERMINISTA (AUTOFIX,
    set_prs). NO toca sufijos que ya son posesivos (su/mi/tu → los deja a POSES/
    CONCORD para la concordancia de número) ni objetos verbales (solo SUBS/ADJ)."""
    m = hw.get('he_morph') or ''
    if not m.startswith(('SUBS', 'ADJ')):
        return None
    prs = hw.get('prs_suffix')
    if not isinstance(prs, dict):
        return None
    pm = (prs.get('he_morph') or '')
    if not pm.upper().startswith('PRS'):
        return None
    suf_es = (prs.get('es') or '').strip()
    if not suf_es or ' ' in suf_es or suf_es.lower() not in _GLOSA_FUNC:
        return None
    if poss_person(suf_es) is not None:      # ya es posesivo → POSES/CONCORD
        return None
    # el STEM debe ser un sustantivo real: si está vacío o es funcional, restaurar
    # solo el posesivo daría un «su» SUELTO (falta el sustantivo) → no tocar aún
    # (lo resuelve check_glosafunc en la raíz; converge en una corrida posterior).
    stem_es = (hw.get('es') or '').strip()
    if not stem_es or stem_es.lower() in _GLOSA_FUNC:
        return None
    person = suffix_person(pm)
    onum = suffix_owner_number(pm)
    if not person or not onum:
        return None
    gender = 'f' if '.F' in m else 'm'
    noun_num = 'p' if ('.PL' in m or '.DU' in m) else 's'
    new = spanish_poss(person, onum, gender, noun_num)
    if not new or new.lower() == suf_es.lower():
        return None
    if new.lower() in _palabras_token_es(hw, con_suf=False):   # no duplicar
        return None
    return (f'sufijo posesivo ({pm}) glosado como palabra funcional «{suf_es}» '
            f'→ «{new}» (la morfología del sufijo manda)',
            ('set_prs', new, prs.get('es') or ''))


# pronombre SUJETO español inequívoco → (persona, número). Solo formas tónicas de
# sujeto (no «tu» posesivo, no «el» artículo; exige «tú»/«él» con tilde). Sirve para
# detectar una glosa verbal cuyo pronombre sujeto CONTRADICE la morfología hebrea.
_SUBJ_PRON_PN = {
    'yo': ('1', 'SG'), 'nosotros': ('1', 'PL'), 'nosotras': ('1', 'PL'),
    'tú': ('2', 'SG'), 'vosotros': ('2', 'PL'), 'vosotras': ('2', 'PL'),
    'él': ('3', 'SG'), 'ella': ('3', 'SG'),
    'ellos': ('3', 'PL'), 'ellas': ('3', 'PL'),
}


def check_morfo(hw):
    """Concordancia glosa↔morfología verbal (versión CONSERVADORA, report-only).

    Señales de alta precisión, validadas contra los capítulos cerrados para no
    marcar glosas correctas:
      (a) morfología FINITA (incl. imperativo) pero la glosa es un INFINITIVO
          crudo de una sola palabra (p.ej. WAYYIQT glosado «beber»).
      (b) desajuste de PERSONA en PRETÉRITO (QATAL/WAYYIQT) con terminación
          acentuada inequívoca: 3ª pers. con «-é/-í» (1ª sg) o 1ª pers. con
          «-ó/-ió» (3ª sg).
      (d) PRONOMBRE SUJETO explícito en la glosa que contradice la persona/número
          de la morfología (p.ej. «él estuvo» 3ª sg en un verbo P3.PL): glosa
          parafraseada/contaminada (Gén 26:8 אָרְכוּ «se alargaron», que quedó
          «después que él estuvo»).
    NO evalúa número por la sola terminación del verbo (colectivos e imperativos en
    -n dan falsos positivos); solo cuando hay un PRONOMBRE sujeto inequívoco. Tampoco
    marca infinitivos hebreos (INFA/INFC) que en español van como verbo finito."""
    m = hw.get('he_morph') or ''
    es = (hw.get('es') or '').strip()
    if not es or not _is_finite_verb(m):
        return []
    out = []
    toks = [t for t in re.split(r'\s+', es.lower()) if t]

    # (d) pronombre SUJETO explícito que no concuerda con persona/número del verbo.
    #     Alta precisión: el pronombre es inequívoco y no va tras preposición
    #     (excluye oblicuos «a él/para ella»). Report-only (la glosa la eliges tú).
    per, num = _morph_person(m), _morph_number(m)
    if per and num:
        prev = ''
        for t in toks:
            tc = t.strip('¿?¡!.,;:«»“”\'()-')
            pn = _SUBJ_PRON_PN.get(tc)
            if pn and prev not in PREP_HEADS and (pn[0] != per or pn[1] != num):
                out.append(f'morf verbal {m} ({per}ª {num}) pero la glosa lleva '
                           f'pronombre sujeto «{tc}» ({pn[0]}ª {pn[1]}) que no '
                           f'concuerda: «{es}»')
                break
            prev = tc

    # (a) morfología finita pero glosa = INFINITIVO (una sola palabra, con posible
    #     enclítico pegado: «beber», «beberle», «bajarla»). El verbo debe ir
    #     CONJUGADO al tiempo/persona del hebreo. Reporte + sugerencia de la forma
    #     finita (pretérito 3ª pers. para narrativo). NO se auto-aplica: en tallos
    #     derivados (Hifil causativo) la glosa base puede ser además el lexema
    #     equivocado («beber» → debe ser «dar de beber»), y la palabra la eliges tú.
    if len(toks) == 1:
        base = _quitar_enclitics(toks[0])
        if _INF_RE.match(base):
            if _tiempo_autofix(hw):
                return out  # lo corrige TIEMPOVERBAL (autofix); no duplicar reporte
            per, num = _morph_person(m), _morph_number(m)
            sug = ''
            if per == '3' and num and 'SEQ' not in m and \
                    any(t in m for t in ('WAYYIQT', 'WATIQT', 'QATAL')):
                p3 = _pret_3(base, num)
                if p3:
                    sug = f' → pretérito {"sg" if num == "SG" else "pl"} «{p3}»'
            out.append(f'morf finita ({m}) pero glosa en infinitivo «{es}»; '
                       f'debe ir en verbo finito{sug}')
            return out
        # (a2) verbo finito ACTIVO CON SUFIJO DE OBJETO pronominal pero glosa =
        #      PARTICIPIO PASADO crudo («los cegado», «los llenado», «te tocado»).
        #      Señal de ALTA PRECISIÓN: un participio pasado NO admite objeto
        #      enclítico («*los cegado» es agramatical); el objeto prueba que es un
        #      verbo finito transitivo → debe ir en PRETÉRITO («los cegaron», «te
        #      tocamos»). Exigir el sufijo de objeto evita los falsos positivos de
        #      participios legítimos SIN objeto (perfecto «hemos hallado»,
        #      adjetival «avanzado en días», «había bendecido»). ACOTADO a binyanim
        #      ACTIVOS (QAL/PIEL/HIF). Reporte + sugerencia en personas seguras; NO
        #      se auto-aplica (irregulares/causativo pueden cambiar el lexema).
        if (_PART_RE.match(toks[0]) and any(b in m for b in ('QAL', 'PIEL', 'HIF'))
                and prs_morph(hw).startswith('PRS')):
            per, num = _morph_person(m), _morph_number(m)
            pv = _part_pret(toks[0], per, num)
            obj = prs_es(hw).strip()
            render_malo = combinar_es(toks[0], obj, m)
            sug = f' → «{pv}»' if pv else ''
            out.append(f'morf finita activa con objeto ({m}) pero glosa en '
                       f'PARTICIPIO: render «{render_malo}» (participio no admite '
                       f'objeto enclítico) → verbo finito{sug}')
            return out

    # (c) TIEMPO: wayyiqtol/wayyiqtol-fem (WAYYIQT/WATIQT) = narrativo PRETÉRITO;
    #     su glosa española jamás debe ir en FUTURO (se levantará, dirá, será…).
    #     Excluye SEQ.PERF/weqatal, que sí admite lectura futura/modal.
    if any(t in m for t in ('WAYYIQT', 'WATIQT')) and 'SEQ' not in m:
        h = _verb_head(es)
        if h and _FUT_RE.search(h):
            out.append(f'morf WAYYIQT pretérito narrativo ({m}) pero glosa en '
                       f'FUTURO «{h}» → debe ir en pasado')

    # (c2) SIMÉTRICO de (c): IMPERFECTO hebreo (IMPF/yiqtol) = futuro/presente/
    #      modal; su glosa NO debería ir en PRETÉRITO INDEFINIDO español (-ó/-aron):
    #      eso es lectura de wayyiqtol/qatal, no de yiqtol. El imperfecto habitual
    #      español (-aba/-ía) y el futuro (-rá) SÍ son válidos y NO se marcan.
    #      Excluye SEQ (weyiqtol/consecutivo), JUSS y COHORT (volitivos). Report-
    #      only: la lectura del yiqtol depende del contexto y la palabra la eliges tú.
    if 'IMPF' in m and not any(t in m for t in ('SEQ', 'JUSS', 'COHORT', 'IMPV')):
        h = _verb_head(es)
        if h and len(h) >= 4 and not _INF_RE.match(h) and _PRET_IND_RE.search(h):
            out.append(f'morf IMPF/yiqtol ({m}) pero glosa en PRETÉRITO «{h}» → '
                       f'el yiqtol va en futuro/presente/modal (o imperfecto -aba/-ía)')

    # (c3) VOLITIVOS: yusivo (JUSS) y cohortativo (COHORT) son modales
    #      («que + subjuntivo», «vaya», «hagamos», «vamos a»); jamás pretérito
    #      indefinido puntual (-ó/-aron). El subjuntivo/imperativo (-e/-a/-emos/-amos)
    #      NO acaba en pretérito acentuado → sin falsos positivos. Excluye SEQ.
    #      Report-only: la forma volitiva exacta la eliges tú.
    if any(t in m for t in ('JUSS', 'COHORT')) and 'SEQ' not in m:
        h = _verb_head(es)
        if h and len(h) >= 4 and not _INF_RE.match(h) and _PRET_IND_RE.search(h):
            modo = 'yusivo' if 'JUSS' in m else 'cohortativo'
            out.append(f'morf {modo} ({m}) pero glosa en PRETÉRITO «{h}» → volitivo '
                       f'(subjuntivo/imperativo), no pasado puntual')

    # (b) persona en PRETÉRITO real (QATAL/WAYYIQT), terminación acentuada.
    #     Excluye SEQ.PERF/weqatal (modal→subjuntivo «esté»), futuros y
    #     monosílabos (exige ≥4 letras) para no marcar subjuntivos válidos.
    if 'SEQ' in m or not any(t in m for t in ('QATAL', 'WAYYIQT', 'WATIQT')):
        return out
    head = _verb_head(es)
    if not head or len(head) < 4 or _INF_RE.match(head):
        return out
    per = _morph_person(m)
    if per == '3' and _P1SG_ACC_RE.search(head) and not _P3SG_ACC_RE.search(head):
        out.append(f'morf 3ª persona ({m}) pero glosa 1ª sg «{head}»')
    elif per == '1' and _P3SG_ACC_RE.search(head):
        out.append(f'morf 1ª persona ({m}) pero glosa 3ª sg «{head}»')

    return out


# ── Motor principal ─────────────────────────────────────────────────────────
def run(d, slug, rng, src, min_fuente, cats):
    lo, hi = rng
    canon = build_canon(d, *src, min_fuente) if 'CANON' in cats else {}
    glob_prot, ctx_prot = load_protected(slug)

    # vocabulario del usuario (glosas capitalizadas intencionales del rango fuente)
    vocab = set()
    if 'RECORRIDO' in cats:
        cnt = Counter()
        for v in d['verses']:
            if not in_range(v['chapter'], v['verse'], *src):
                continue
            for p in v.get('pairs') or []:
                for hw in p.get('he_words') or []:
                    m = hw.get('he_morph') or ''
                    if is_nprop_gent(m) or is_tetra(hw):
                        continue
                    es = (hw.get('es') or '').strip()
                    if es and es[0].isupper() and any(c.islower() for c in es[1:]):
                        cnt[es] += 1
        vocab = {e for e, n in cnt.items() if n >= 2}

    findings: list[F] = []

    for v in d['verses']:
        ch, vs = v['chapter'], v['verse']
        if not in_range(ch, vs, lo, hi):
            continue
        flat = []
        for pi, p in enumerate(v.get('pairs') or []):
            if p.get('kind') == 'gk_add':
                continue
            for wi, hw in enumerate(p.get('he_words') or []):
                flat.append((pi, wi, hw))

        for idx, (pi, wi, hw) in enumerate(flat):
            m = hw.get('he_morph') or ''
            es = (hw.get('es') or '').strip()
            he = hw.get('he_form') or ''
            prot = (ch, vs, pi, wi) in ctx_prot

            if 'MALFORM' in cats:
                why = check_malform(hw)
                if why:
                    findings.append(F('MALFORM', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'PUNTOCOMA' in cats:
                r = check_puntocoma(hw)
                if r:
                    findings.append(F('PUNTOCOMA', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'VACIO' in cats:
                for _role, why in check_vacio(hw):
                    findings.append(F('VACIO', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'CORTO' in cats:
                why = check_corto(hw)
                if why:
                    findings.append(F('CORTO', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'LARGO' in cats:
                why = check_largo(hw)
                if why:
                    findings.append(F('LARGO', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'CONCORD' in cats:
                for why, sug in check_concord(hw):
                    findings.append(F('CONCORD', ch, vs, pi, wi, he, m, why,
                                      suggest=sug, protected=prot))

            if 'PRON' in cats:
                for why, sug in check_pron(hw):
                    findings.append(F('PRON', ch, vs, pi, wi, he, m, why,
                                      suggest=sug, protected=prot))

            if 'POSES' in cats:
                r = check_poses(hw)
                if r:
                    findings.append(F('POSES', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'PREPRON' in cats:
                r = check_prep_pron(hw)
                if r:
                    findings.append(F('PREPRON', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'MORPH_MISMATCH' in cats:
                why = check_morph_mismatch(hw)
                if why:
                    findings.append(F('MORPH_MISMATCH', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'HOMOGRAF' in cats:
                r = check_homograf(hw)
                if r:
                    findings.append(F('HOMOGRAF', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'REFLEX' in cats:
                r = check_reflexivo(hw)
                if r:
                    findings.append(F('REFLEX', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'EUFONIA' in cats:
                for idx, nuevo, viejo, why in check_eufonia(hw):
                    findings.append(F('EUFONIA', ch, vs, pi, wi, he, m, why,
                                      suggest=('pfx_set', idx, nuevo, viejo),
                                      protected=prot))

            if 'VAV' in cats:
                for idx, viejo in check_vav_wayyiqtol(hw):
                    nuevo = 'Y' if (viejo or '')[:1].isupper() else 'y'
                    _es_prop = (viejo or '').strip().lower() in _VAV_PROPOSITO
                    _tipo = ('conjunción de propósito' if _es_prop
                             else 'valor indebido para el vav narrativo')
                    findings.append(F('VAV', ch, vs, pi, wi, he, m,
                                      f'vav consecutivo (wayyiqtol) glosado {viejo!r} '
                                      f'({_tipo}); el vav narrativo '
                                      f'es «y» → «{nuevo}»',
                                      suggest=('pfx_set', idx, nuevo, viejo),
                                      protected=prot))

            if 'KI' in cats:
                for det, sug, fld in check_ki(hw):
                    findings.append(F('KI', ch, vs, pi, wi, he, m, det,
                                      suggest=sug, field=fld, protected=prot))

            if 'PEN' in cats:
                for det, sug, fld in check_pen(hw):
                    findings.append(F('PEN', ch, vs, pi, wi, he, m, det,
                                      suggest=sug, field=fld, protected=prot))

            if 'CONJUGA' in cats:
                r = check_conjuga(hw)
                if r:
                    findings.append(F('CONJUGA', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'SINTAXIS' in cats:
                for det, sug in check_sintaxis(hw):
                    findings.append(F('SINTAXIS', ch, vs, pi, wi, he, m, det,
                                      suggest=sug, protected=prot))

            if 'CONSTRUCT' in cats:
                r = check_construct(hw)
                if r:
                    # r = (detalle, «stem de»). Se guarda como set_es aplicable
                    # (old=es actual) para que --apply lo maneje SI CONSTRUCT
                    # entra en AUTOFIX. Opción B: N1 recibe «de», N2 intacto.
                    findings.append(F('CONSTRUCT', ch, vs, pi, wi, he, m, r[0],
                                      suggest=('set_es', r[1], es),
                                      field='es', protected=prot))
                r2 = check_de_espuria(hw)
                if r2:
                    findings.append(F('CONSTRUCT', ch, vs, pi, wi, he, m, r2[0],
                                      suggest=r2[1], field='es', protected=prot))

            if 'MORFO' in cats:
                for why in check_morfo(hw):
                    findings.append(F('MORFO', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'TIEMPOVERBAL' in cats:
                r = check_tiempo_finito(hw)
                if r:
                    findings.append(F('TIEMPOVERBAL', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'ENCLIT' in cats:
                r = check_enclit(hw)
                if r:
                    findings.append(F('ENCLIT', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'GLOSAFUNC' in cats:
                r = check_glosafunc(hw)
                if r:
                    findings.append(F('GLOSAFUNC', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))
                rs = check_suf_func(hw)
                if rs:
                    findings.append(F('GLOSAFUNC', ch, vs, pi, wi, he, m, rs[0],
                                      suggest=rs[1], protected=prot))

            if 'RENDER' in cats:
                r = check_render(hw)
                if r:
                    findings.append(F('RENDER', ch, vs, pi, wi, he, m, r[0],
                                      suggest=r[1], protected=prot))

            if 'TRANSLIT' in cats:
                why = check_translit(hw)
                if why:
                    if isinstance(why, tuple):
                        findings.append(F('TRANSLIT', ch, vs, pi, wi, he, m, why[0],
                                          suggest=why[1], protected=prot))
                    else:
                        findings.append(F('TRANSLIT', ch, vs, pi, wi, he, m, why,
                                          protected=prot))
                lex = check_translit_lexema(hw)
                if lex:
                    findings.append(F('TRANSLIT', ch, vs, pi, wi, he, m, lex[0],
                                      suggest=lex[1], field='es', protected=prot))
                for _chk in (check_translit_barak_verb,
                             check_translit_beraja_qelala_suf):
                    _tr = _chk(hw)
                    if _tr:
                        findings.append(F('TRANSLIT', ch, vs, pi, wi, he, m, _tr[0],
                                          suggest=_tr[1], field='es', protected=prot))
                        break

            if ('SINSTRONG' in cats and inferir_strongs is not None
                    and not (hw.get('strongs') or '').strip() and he):
                inf = inferir_strongs.inferir(consk(he), m)
                if inf:
                    why = (f'sin Strong → probablemente {inf[0]} '
                           f'({inf[1]}%, n={inf[2]}, {inf[3]})')
                else:
                    why = 'sin Strong y sin inferencia clara → a lista (lógica/morfología)'
                findings.append(F('SINSTRONG', ch, vs, pi, wi, he, m, why, protected=prot))

            if ('REFUERZO' in cats and estilo_usuario is not None and es and not prot
                    and not looks_proper(es) and not is_nprop_gent(m)):
                st_rf = hw.get('strongs') or ''
                pick_rf = estilo_usuario.sugerir(st_rf, m, es)
                if not (pick_rf and pick_rf.get('via') == 'verde'):
                    sk_rf = consk(he)
                    pick_rf = estilo_usuario.sugerir_sk(sk_rf, m, es) if sk_rf else None
                if pick_rf and pick_rf.get('via') == 'verde':
                    why = (f'verde: «{es}» → «{pick_rf["sugerida"]}» '
                           f'(tu corrección de estilo; el hebreo solo identifica)')
                    findings.append(F('REFUERZO', ch, vs, pi, wi, he, m, why,
                                      suggest=('set_es', pick_rf['sugerida'], es),
                                      field='es', protected=prot))
                    # no duplicar en ESTILO
                    pass

            if ('ESTILO' in cats and estilo_usuario is not None and es and not prot
                    and not looks_proper(es) and not is_nprop_gent(m)
                    and es.lower() not in _GLOSA_FUNC):   # corrupción funcional → GLOSAFUNC
                st_es = hw.get('strongs') or ''
                prev_ck = consk(flat[idx - 1][2].get('he_form') or '') if idx > 0 else '∅'
                next_ck = (consk(flat[idx + 1][2].get('he_form') or '')
                           if idx + 1 < len(flat) else '∅')
                # 1) por Strong (preferida global, luego contexto)
                pick = estilo_usuario.sugerir(st_es, m, es)
                if pick and pick.get('via') == 'verde':
                    pick = None  # lo cubre REFUERZO (autofix)
                if not pick:
                    pick = estilo_usuario.sugerir_ctx(st_es, m, es, prev_ck, next_ck)
                # 2) RESPALDO por esqueleto cuando el Strong no ayuda (falta o sin
                #    datos): cubre tokens sin strong (מלאך→mensajero, שם→allí…).
                if not pick and not is_nprop_gent(m):
                    sk = consk(he)
                    if sk:
                        pick = (estilo_usuario.sugerir_sk(sk, m, es)
                                or estilo_usuario.sugerir_ctx_sk(sk, m, es, prev_ck, next_ck))
                    if pick and pick.get('via') == 'verde':
                        pick = None
                if pick:
                    if 'ctx' in pick:
                        why = (f'en contexto {pick["ctx"]} sueles escribir '
                               f'«{pick["sugerida"]}» ({pick["pct"]}%, n={pick["n"]}); '
                               f'aquí está «{es}»')
                    else:
                        why = (f'sueles escribir «{pick["sugerida"]}» ({pick["pct"]}%, '
                               f'n={pick["n"]}) para esta forma; aquí está «{es}»'
                               + (f' ({pick["actual_pct"]}%)' if pick.get("actual_pct")
                                  else ' (raro en tu uso)'))
                    if pick.get('via') == 'esqueleto':
                        why += ' [por esqueleto, sin strong]'
                    findings.append(F('ESTILO', ch, vs, pi, wi, he, m, why,
                                      suggest=('set_es', pick['sugerida'], es),
                                      protected=prot))

            if 'RECORRIDO' in cats:
                why = check_recorrido_nprop(hw, idx == 0, glob_prot, prot, vocab)
                if why:
                    findings.append(F('RECORRIDO', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'YHWH' in cats:
                why = check_yhwh(hw)
                if why:
                    findings.append(F('YHWH', ch, vs, pi, wi, he, m, why, protected=prot))

            if 'PENINSULAR' in cats:
                for field, fidx, old, new in check_peninsular(hw):
                    findings.append(F('PENINSULAR', ch, vs, pi, wi, he, m,
                                      f'{field}{"["+str(fidx)+"]" if fidx is not None else ""}: {old!r}→{new!r}',
                                      suggest=(field, fidx, old, new), field=field, protected=prot))

            if 'CANON' in cats and not is_nprop_gent(m) and not is_tetra(hw) and not prot:
                st = (hw.get('strongs') or '').strip()
                if st and st not in glob_prot and es:
                    k = canon_key(hw)
                    if k in canon and canon[k] != es:
                        findings.append(F('CANON', ch, vs, pi, wi, he, m,
                                          f'{es!r} → {canon[k]!r}',
                                          suggest=('set_es', canon[k], es),
                                          field='es', protected=prot))

        # ── chequeos a nivel de versículo (render) ──
        # CONCORD de DEMOSTRATIVO suelto: el NÚMERO lo fija la morfología hebrea
        # (.PL/.DU→plural, autoridad); el GÉNERO lo fija el sustantivo referente
        # ESPAÑOL (no el hebreo, para no romper דּוֹר masc → «generación» fem). La
        # dirección (atributivo tras el sustantivo vs predicativo antes) la resuelve
        # demo_referent_gender por adyacencia → así «tierra esta» (זֹאת) NO se toca y
        # «estas años» (אֵלֶּה) sí → «estos años» (25:16-17). Autofix solo si el
        # referente tiene género CONOCIDO.
        #   Cubre además el DEMOSTRATIVO PENTATEUCAL הַהוּא/הַהִוא, que el morfólogo
        #   etiqueta PRON.PERS (no DEM): «tierra … aquel» (הִוא fem, 2:12) → «aquella»
        #   por el referente ESPAÑOL «tierra». Como el género lo fija el sustantivo
        #   español (no el hebreo), NO rompe «aquella noche»/«aquel año»/«aquel
        #   tiempo» (donde לילה/שנה/עת divergen de género con noche/año/tiempo).
        if 'CONCORD' in cats:
            for idx, (pi, wi, hw) in enumerate(flat):
                m = hw.get('he_morph') or ''
                if 'DEM' not in m and morph_root(m) != 'PRON':
                    continue
                es0 = (hw.get('es') or '').strip()
                cur = es0.lower()
                if cur not in DEMO_FAM:
                    continue
                # PRON.PERS (demostrativo PENTATEUCAL הַהוּא/הַהִוא): corrige SOLO el
                # uso ATRIBUTIVO — sustantivo COMÚN inmediatamente ANTES («tierra
                # aquel»→«aquella»). Excluye el COPULATIVO «Luz … esta [es] Bet-El»
                # (Gén 35:6), donde el referente es un nombre PROPIO y el detector no
                # puede fijar género con certeza (evita falsos «este»).
                if 'DEM' not in m:
                    prev_comun = False
                    for j in range(idx - 1, -1, -1):
                        w = flat[j][2]
                        if not (w.get('es') or '').strip():
                            continue
                        mm = w.get('he_morph') or ''
                        prev_comun = (morph_root(mm) in ('SUBS', 'ADJ')
                                      and not is_nprop_gent(mm))
                        break
                    if not prev_comun:
                        continue
                heb_num = 'p' if ('.PL' in m or '.DU' in m) else 's'
                g = demo_referent_gender(flat, idx)
                if not g:
                    continue
                exp = DEMO_TABLE[DEMO_FAM[cur]][(g, heb_num)]
                if exp == cur:
                    continue
                new = exp.capitalize() if es0[:1].isupper() else exp
                findings.append(F('CONCORD', ch, vs, pi, wi,
                                  hw.get('he_form') or '', m,
                                  f'demostrativo {es0!r} no concuerda en '
                                  f'género/número ({g}/{heb_num}) → {new!r}',
                                  suggest=('set_es', new, es0), field='es',
                                  protected=(ch, vs, pi, wi) in ctx_prot))

        if 'CONTAGIO' in cats:
            for (cpi, cwi, chef, cm, cdet, csug) in check_contagio(flat):
                findings.append(F('CONTAGIO', ch, vs, cpi, cwi, chef, cm, cdet,
                                  suggest=csug,
                                  protected=(ch, vs, cpi, cwi) in ctx_prot))

        if 'RECORRIDO' in cats:
            for i in range(1, len(flat)):
                cur = flat[i][2]; prev = flat[i - 1][2]
                ce = (cur.get('es') or '').strip(); pe = (prev.get('es') or '').strip()
                cm = cur.get('he_morph') or ''; pm = prev.get('he_morph') or ''
                if not ce or ce != pe or len(ce) <= 2:
                    continue
                if is_nprop_gent(cm) or is_nprop_gent(pm):
                    continue
                if cur.get('strongs') and cur.get('strongs') == prev.get('strongs') and cm == pm:
                    continue
                # REPETICIÓN HEBREA REAL: si la forma consonántica del token y su
                # vecino es idéntica, la doble glosa es fiel al texto, no un
                # recorrido (אָדֹם אָדֹם 25:30, בֵּין…בֵּין 26:28, קוֹל קוֹל 27:22).
                # Cubre el caso frecuente en que falta/difiere el Strong.
                if consk(cur.get('he_form') or '') == consk(prev.get('he_form') or ''):
                    continue
                findings.append(F('RECORRIDO', ch, vs, flat[i][0], flat[i][1],
                                  cur.get('he_form') or '', cm,
                                  f'repetido con vecino ({prev.get("he_form")!r}={pe!r})',
                                  protected=(ch, vs, flat[i][0], flat[i][1]) in ctx_prot))

        if 'DOBLE' in cats:
            # render del versículo por token → detectar dobles y apilamiento posesivo
            toks = []
            for (pi, wi, hw) in flat:
                r = render_token(hw)
                for w in r.split():
                    toks.append((w, pi, wi))
            for i in range(1, len(toks)):
                w0 = toks[i - 1][0].lower(); w1 = toks[i][0].lower()
                # solo palabras funcionales: "el el", "de de", "su su". Los dobles
                # de contenido o nombre propio ("Abraham Abraham") son legítimos.
                if w0 == w1 and len(w1) > 1 and w1 in DOUBLE_FUNC:
                    findings.append(F('DOBLE', ch, vs, toks[i][1], toks[i][2], '', '',
                                      f'palabra repetida «{w1}» (render)'))

    return findings, canon, len(ctx_prot), len(glob_prot)


def apply_safe(d, findings, slug=None):
    """Aplica SOLO el conjunto AUTOFIX (hoy: CANON, PENINSULAR, CONSTRUCT, POSES,
    CONCORD, PRON, HOMOGRAF, EUFONIA). Cada op verifica el valor previo
    (idempotente):
      · CANON/CONSTRUCT/ESTILO→ set_es (raíz)
      · PENINSULAR            → es/prefix/suf según campo
      · CONCORD               → pfx_set (posesivos su→sus Y artículos el/la/los/las
                                cuando el género es seguro) / set_prs
      · TRANSLIT              → set_es (mayúscula de nombre propio: cananeos→Cananeos)
      · POSES                 → clear_prs (sufijo redundante) / set_es (posesivo
                                largo/tónico espurio) / poss_rehome (posesivo de
                                raíz que no concuerda con el sufijo hebreo →
                                reconstruye desde el sufijo y limpia)
      · PRON                  → set_es (quita pronombre) / idiom
      · HOMOGRAF              → set_es (שם→allí, שֵׁם→nombre)
      · EUFONIA               → pfx_set (conjunción y↔e ante sonido i-)
      · CONJUGA               → set_es (forma verbal inexistente: salan→salen)
      · TIEMPOVERBAL          → set_es (verbo finito glosado como infinitivo →
                                pretérito 3ª pers.; SOLO QAL -ar/tabulado, sin
                                enclítico/reflexivo; Hifil e irregulares → reporte)
      · PUNTOCOMA             → set_es (arrastre RVR «BUENO; resto»→«BUENO»;
                                los ambiguos van SOLO a reporte, suggest=None)
    Respeta el CANDADO: nunca modifica capítulos terminados/bloqueados.
    """
    def get_hw(ch, vs, pi, wi):
        for v in d['verses']:
            if v['chapter'] != ch or v['verse'] != vs:
                continue
            pairs = v.get('pairs') or []
            if pi >= len(pairs):
                return None
            hws = pairs[pi].get('he_words') or []
            return hws[wi] if wi < len(hws) else None
        return None

    n = 0
    bloqueados = 0
    for f in findings:
        if f.cat not in AUTOFIX or f.protected or not f.suggest:
            continue
        if slug is not None and esta_bloqueado(slug, f.ch):
            bloqueados += 1
            continue
        hw = get_hw(f.ch, f.vs, f.pi, f.wi)
        if hw is None:
            continue
        sg = f.suggest

        if f.cat == 'PENINSULAR':
            field, fidx, old, new = sg
            if field == 'es' and (hw.get('es') or '') == old:
                hw['es'] = new; n += 1
            elif field == 'suf':
                prs = hw.get('prs_suffix') or {}
                if (prs.get('es') or '') == old:
                    prs['es'] = new; hw['prs_suffix'] = prs; n += 1
            elif field == 'prefix':
                arr = hw.get('prefix_es') or []
                if fidx is not None and fidx < len(arr) and arr[fidx] == old:
                    arr[fidx] = new; n += 1
            continue

        op = sg[0]
        if op == 'set_es':
            new = sg[1]; old = sg[2] if len(sg) > 2 else None
            if old is None:
                if hw.get('es'):
                    hw['es'] = new; n += 1
            elif (hw.get('es') or '') == old:
                hw['es'] = new; n += 1
        elif op == 'idiom':
            new, old = sg[1], sg[2]
            if (hw.get('es') or '') == old:
                hw['es'] = new
                prs = hw.get('prs_suffix')
                if isinstance(prs, dict):
                    prs['es'] = ''
                n += 1
        elif op == 'pfx_set':
            idx, new, old = sg[1], sg[2], sg[3]
            # CONCORD: se auto-aplican los POSESIVOS de prefijo (su→sus, mi→mis…)
            # Y los ARTÍCULOS (el/la/los/las). El artículo SOLO se marca cuando el
            # género/número del sustantivo español es SEGURO: expected_article
            # devuelve None ante cualquier ambigüedad y las excepciones peligrosas
            # (tribu/maná/día/mano/agua…) están tabuladas en FEM_O/MASC_A/A_TONICA.
            # Es concordancia de la MISMA palabra → error gramatical objetivo,
            # no elección de estilo («el tienda»→«la tienda»).
            if f.cat == 'CONCORD' and new.lower() not in POSSESSIVES \
                    and new.lower() not in ARTICLES_ES:
                continue
            arr = hw.get('prefix_es') or []
            if idx < len(arr) and arr[idx] == old:
                arr[idx] = new; n += 1
        elif op == 'pfx_clear':
            idx, old = sg[1], sg[2]
            arr = hw.get('prefix_es') or []
            if idx < len(arr) and arr[idx] == old:
                arr[idx] = ''; n += 1
        elif op == 'clear_prs':
            old = sg[1]
            prs = hw.get('prs_suffix')
            if isinstance(prs, dict) and (prs.get('es') or '') == old:
                prs['es'] = ''; n += 1
        elif op == 'poss_rehome':
            # POSES: raíz con posesivo espurio + sufijo autoridad. Reconstruye el
            # posesivo correcto en la raíz y limpia el sufijo (idempotente: exige
            # que raíz y sufijo sigan en el estado previo).
            old_stem, new_stem, old_suf = sg[1], sg[2], sg[3]
            prs = hw.get('prs_suffix')
            if ((hw.get('es') or '') == old_stem
                    and isinstance(prs, dict) and (prs.get('es') or '') == old_suf):
                hw['es'] = new_stem
                prs['es'] = ''
                n += 1
        elif op == 'set_prs':
            new, old = sg[1], sg[2]
            prs = hw.get('prs_suffix')
            if isinstance(prs, dict) and (prs.get('es') or '') == old:
                prs['es'] = new; n += 1
    if bloqueados:
        print(f"CANDADO: {bloqueados} arreglo(s) OMITIDO(s) por caer en capítulos bloqueados de «{slug}».")
    return n


# ── BARRERA DE INMUTABILIDAD ────────────────────────────────────────────────
# El motor de español SOLO puede tocar estos campos del lado español. TODO lo
# demás (hebreo, griego, strongs, morfología, orden de versos/pares/palabras) es
# INTOCABLE y se verifica byte a byte tras --apply. Es una garantía dura y
# verificable: si el motor alterase cualquier otra cosa, aborta sin escribir.
_CAMPOS_ESCRIBIBLES_ES = ('es', 'es_source', 'prefix_es')  # + prs_suffix.es


def _huella_intocable(d):
    """Huella determinista de TODO lo que el motor NO debe modificar: por cada
    token, su dict completo salvo los campos escribibles del español; más la
    estructura y el ORDEN (cap:vs, nº de pares, nº de palabras). Comparar esta
    huella antes/después de --apply garantiza que no se tocó hebreo, griego,
    strongs, morfología ni se reordenó nada."""
    filas = []
    for v in d.get('verses', []):
        fila = [v.get('chapter'), v.get('verse'), len(v.get('pairs') or [])]
        for p in (v.get('pairs') or []):
            hws = p.get('he_words') or []
            fila.append(len(hws))
            for hw in hws:
                t = dict(hw)
                for k in _CAMPOS_ESCRIBIBLES_ES:
                    t.pop(k, None)
                prs = t.get('prs_suffix')
                if isinstance(prs, dict):
                    prs = dict(prs)
                    prs.pop('es', None)     # prs_suffix.es SÍ es escribible
                    t['prs_suffix'] = prs   # he_form/he_morph/gr_word: INTOCABLES
                fila.append(json.dumps(t, ensure_ascii=False, sort_keys=True))
        filas.append(tuple(fila))
    return filas


def _verificar_intocable(antes, despues):
    """Lista de violaciones (vacía = solo se tocaron campos permitidos)."""
    if len(antes) != len(despues):
        return [f'cambió el nº de versos: {len(antes)}→{len(despues)}']
    difs = []
    for a, b in zip(antes, despues):
        if a != b:
            difs.append(f'{b[0]}:{b[1]}')
    return difs


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser(description='Motor unificado de revisión del español.')
    ap.add_argument('--book', default='genesis')
    ap.add_argument('--chapter', type=int, help='atajo: revisa un capítulo entero')
    ap.add_argument('--from', dest='dst_from')
    ap.add_argument('--to', dest='dst_to')
    ap.add_argument('--source-from', default='1:1')
    ap.add_argument('--source-to', default=None,
                    help='tope del canon (cap:verso). Por defecto: último capítulo cerrado.')
    ap.add_argument('--min-fuente', type=int, default=2)
    ap.add_argument('--only', nargs='*', help=f'categorías: {" ".join(CATEGORIES)}')
    ap.add_argument('--skip', nargs='*', default=[])
    ap.add_argument('--apply', action='store_true',
                    help=f'aplica arreglos seguros ({" + ".join(sorted(AUTOFIX))})')
    ap.add_argument('--max', type=int, default=60, help='detalle por categoría')
    ap.add_argument('--export', metavar='RUTA.json',
                    help='vuelca todos los hallazgos serializados a JSON (para diffs, '
                         'dashboards o contexto estructurado; no altera datos)')
    args = ap.parse_args()

    dm = DATA / f'{args.book}_final.json'
    if not dm.exists():
        print(f'No existe {dm}')
        return 1
    _raw = dm.read_text(encoding='utf-8')
    d = json.loads(_raw)
    # ¿el archivo está minificado (como lo escribe el servidor con separators
    # compactos)? → hay que RESPETAR ese formato al reescribir con --apply, para
    # no reformatear todo el JSON (diff gigante y cambio del orden de la base).
    _minificado = _raw[:4000].count('\n') < 5

    if args.chapter is not None:
        lo, hi = (args.chapter, 0), (args.chapter, 10 ** 6)
        etiqueta = f'{args.book} cap {args.chapter}'
    elif args.dst_from:
        lo = parse_ref(args.dst_from)
        hi = parse_ref(args.dst_to) if args.dst_to else (lo[0], 10 ** 6)
        etiqueta = f'{args.book} {args.dst_from}–{args.dst_to or "fin"}'
    else:
        lo, hi = (1, 0), (10 ** 6, 10 ** 6)
        etiqueta = f'{args.book} (libro completo)'

    # SINSTRONG (inferencia de Strong faltante) NO entra en la corrida por
    # defecto para no saturar; se pide con --only SINSTRONG o vía inferir_strongs.py.
    cats = set(args.only) if args.only else (set(CATEGORIES) - {'SINSTRONG'})
    cats -= set(args.skip or [])
    bad = cats - set(CATEGORIES)
    if bad:
        print(f'Categorías desconocidas: {bad}. Válidas: {CATEGORIES}')
        return 1

    if not args.source_to:
        args.source_to = default_canon_source_to(args.book, d)
    src = (parse_ref(args.source_from), parse_ref(args.source_to))
    findings, canon, n_ctx, n_glob = run(d, args.book, (lo, hi), src, args.min_fuente, cats)

    by = defaultdict(list)
    for f in findings:
        by[f.cat].append(f)

    print(f"═══ REVISIÓN ES · {etiqueta} · {'APPLY' if args.apply else 'DRY-RUN'} ═══")
    print(f"  Canon fuente {args.source_from}–{args.source_to}: {len(canon)} claves | "
          f"reglas globales: {n_glob} | reglas ctx({args.book}): {n_ctx}")
    print(f"  Categorías: {' '.join(sorted(cats))}")
    print(f"  TOTAL hallazgos: {len(findings)}\n")

    for cat in CATEGORIES:
        if cat not in cats:
            continue
        rows = by.get(cat, [])
        tag = ' (auto-corregible)' if cat in AUTOFIX else ''
        print(f"■ {cat}: {len(rows)}{tag}")
        for r in rows[:args.max]:
            p = ' [PROT]' if r.protected else ''
            if args.book and esta_bloqueado(args.book, r.ch):
                p += ' [CANDADO]'
            print(f"   {r.ch:>3}:{r.vs:<3} p{r.pi:>2}/w{r.wi} {r.he:<13} {r.morph:<22} · {r.detail}{p}")
        if len(rows) > args.max:
            print(f"   … y {len(rows) - args.max} más")
        print()

    if args.export:
        payload = {
            'book': args.book,
            'range': {'from': f'{lo[0]}:{lo[1]}', 'to': f'{hi[0]}:{hi[1]}'},
            'source': {'from': args.source_from, 'to': args.source_to},
            'generated': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'applied': bool(args.apply),
            'total': len(findings),
            'por_categoria': {c: len(by.get(c, [])) for c in CATEGORIES if c in cats},
            'autofix_cats': sorted(AUTOFIX),
            'findings': [finding_to_dict(f) for f in findings],
        }
        Path(args.export).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"EXPORT: {len(findings)} hallazgos → {args.export}\n")

    if not args.apply:
        print(f"(DRY-RUN. Use --apply para corregir SOLO {' + '.join(sorted(AUTOFIX))} con respaldo.)")
        return 0

    _huella_antes = _huella_intocable(d)          # instantánea de lo INTOCABLE
    n = apply_safe(d, findings, slug=args.book)
    try:
        import candado as _cand
        _reaseg = _cand.reasegurar(args.book, d)
        if _reaseg:
            print(f"CANDADO: {_reaseg} verso(s) restaurado(s) desde sello (capítulos cerrados intactos).")
    except Exception:
        pass
    # BARRERA DE INMUTABILIDAD: si el motor tocó algo fuera de {es, prs_suffix.es,
    # prefix_es, es_source}, ABORTA sin escribir (protege hebreo/griego/strongs/
    # morfología/orden). Garantía dura verificada en cada corrida.
    _viol = _verificar_intocable(_huella_antes, _huella_intocable(d))
    if _viol:
        print("✗ ABORTADO: el motor alteró campos INTOCABLES (hebreo/griego/strongs/"
              "morfología/orden). NO se escribió nada. Versos afectados: "
              f"{', '.join(_viol[:20])}{' …' if len(_viol) > 20 else ''}")
        return 2
    if n:
        ts = time.strftime('%Y%m%d_%H%M%S')
        bk = dm.with_suffix(f'.json.bak_revisar_es_{ts}')
        shutil.copyfile(dm, bk)
        _dump = (json.dumps(d, ensure_ascii=False, separators=(',', ':'))
                 if _minificado else json.dumps(d, ensure_ascii=False, indent=1))
        dm.write_text(_dump, encoding='utf-8')
        print(f"APLICADOS (arreglos seguros: {' '.join(sorted(AUTOFIX))}): {n}  ·  respaldo {bk.name}")
    else:
        print("No hubo arreglos seguros que aplicar.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
