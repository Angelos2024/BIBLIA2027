# -*- coding: utf-8 -*-
"""Tests unitarios de motores/scripts/revisar_es.py

Cubre las funciones puras y los chequeos que tocan datos con --apply
(CANON, PENINSULAR, CONSTRUCT) con casos fijos por categoría. Objetivo:
que un ajuste futuro en una lista/heurística NO rompa un caso ya cubierto sin
avisar.

Ejecuta de dos formas:
    python tests/test_revisar_es.py        # runner propio, sin dependencias
    pytest tests/test_revisar_es.py        # si tienes pytest
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / 'motores' / 'scripts'))
import revisar_es as R  # noqa: E402


def hw(strongs='H900001', morph='SUBS.M.SG.A', he='מָקוֹם', es='lugar',
       prefix_es=None, prefix_morphs=None, prs=None):
    """Construye un he_word mínimo para los chequeos."""
    d = {'strongs': strongs, 'he_morph': morph, 'he_form': he, 'es': es}
    if prefix_es is not None:
        d['prefix_es'] = prefix_es
    if prefix_morphs is not None:
        d['prefix_morphs'] = prefix_morphs
    if prs is not None:
        d['prs_suffix'] = prs
    return d


def verse(ch, vs, *hws):
    return {'chapter': ch, 'verse': vs, 'pairs': [{'he_words': list(hws)}]}


# ── es_number ──────────────────────────────────────────────────────────────
def test_es_number_singular_en_s():
    # sustantivos singulares terminados en -s NO son plurales
    assert R.es_number('dios') == 's'
    assert R.es_number('pais') == 's'
    assert R.es_number('mes') == 's'


def test_es_number_plural_y_singular():
    assert R.es_number('casas') == 'p'
    assert R.es_number('lugares') == 'p'
    assert R.es_number('casa') == 's'
    assert R.es_number('mano') == 's'


# ── es_gender ──────────────────────────────────────────────────────────────
def test_es_gender_excepciones_y_regla():
    assert R.es_gender('mano') == 'f'      # FEM_O
    assert R.es_gender('casa') == 'f'      # -a
    assert R.es_gender('libro') == 'm'     # -o
    assert R.es_gender('dias') == 'm'      # plural de «día» (MASC_A) → m


# ── expected_article ─────────────────────────────────────────────────────────
def test_expected_article():
    assert R.expected_article('casa') == 'la'
    assert R.expected_article('casas') == 'las'
    assert R.expected_article('libro') == 'el'
    assert R.expected_article('libros') == 'los'
    # «Dios» se minusculiza y cae en SINGULAR_IN_S → singular masc → «el»
    assert R.expected_article('Dios') == 'el'


# ── combinar_es (render raíz + sufijo) ───────────────────────────────────────
def test_combinar_es_enclitico_infinitivo():
    # infinitivo + clítico objeto → enclítico unido ("llorarla", no "la llorar")
    assert R.combinar_es('llorar', 'la', 'VERBO.QAL.INFC') == 'llorarla'


def test_combinar_es_tonico_sobre_sustantivo():
    # sufijo tónico se pospone: "sepultura él" (check_render luego lo marca)
    assert R.combinar_es('sepultura', 'él', 'SUBS.F.SG.C') == 'sepultura él'


def test_combinar_es_sin_sufijo():
    assert R.combinar_es('casa', '', 'SUBS.F.SG.A') == 'casa'
    assert R.combinar_es('', 'su', '') == 'su'


# ── check_malform ────────────────────────────────────────────────────────────
def test_malform_ingles_bare():
    r = R.check_malform(hw(es='the second'))
    assert r and 'inglés' in r


def test_malform_ingles_sustantivo_contenido():
    # sustantivos de contenido en inglés (womb/seed/nation…) ahora se detectan
    assert R.check_malform(hw(es='womb')) and 'inglés' in R.check_malform(hw(es='womb'))
    assert R.check_malform(hw(es='seed'))
    assert R.check_malform(hw(es='covenant'))
    # «son» NO se marca (colisiona con español «ellos son»)
    assert R.check_malform(hw(es='son')) is None


def test_malform_hebreo_y_dobles():
    assert R.check_malform(hw(es='contiene עברית')) == 'contiene hebreo'
    assert R.check_malform(hw(es='casa  doble')) == 'doble espacio'


def test_malform_limpio_y_none():
    assert R.check_malform(hw(es='casa buena')) is None
    assert R.check_malform(hw(es=None)) is None


# ── check_construct (semikhut, Opción B) ─────────────────────────────────────
def test_construct_flags_bare_construct():
    # LÓGICA BASE del constructo, aislada del modelo de estilo (estilo_usuario=None):
    # un constructo común desnudo pide «de».
    save = R.estilo_usuario
    R.estilo_usuario = None
    try:
        r = R.check_construct(hw(strongs='H1121', morph='SUBS.M.PL.C', he='בְנֵי', es='hijos'))
    finally:
        R.estilo_usuario = save
    assert r is not None and r[1] == 'hijos de'


def test_construct_respeta_estilo_sin_de():
    # POLÍTICA (elección del usuario): CONSTRUCT consulta ESTILO. Si tu uso
    # mayoritario para la forma es «hijos» (sin «de»), NO se añade «de».
    if R.estilo_usuario is None:
        return
    r = R.check_construct(hw(strongs='H1121', morph='SUBS.M.PL.C', he='בְנֵי', es='hijos'))
    assert r is None


def test_construct_excluye_kol():
    assert R.check_construct(hw(morph='SUBS.M.SG.C', he='כֹּל', es='todos')) is None


def test_construct_excluye_numeral():
    assert R.check_construct(hw(morph='ADJ.M.DU.C', he='שְׁנֵי', es='dos')) is None


def test_construct_excluye_nombre_propio_translit():
    assert R.check_construct(hw(morph='SUBS.M.SG.C', he='אֵל', es="'El")) is None


def test_construct_excluye_con_sufijo():
    # con sufijo pronominal el genitivo lo da el sufijo (adoni «mi señor»)
    r = R.check_construct(hw(morph='SUBS.M.SG.C', he='אֲדֹנִי', es='señor',
                             prs={'es': 'mi', 'he_morph': 'PRS.P1.COMMON.SG'}))
    assert r is None


def test_construct_no_reflaga_si_ya_tiene_de():
    assert R.check_construct(hw(morph='SUBS.M.SG.C', he='בֵּית', es='casa de')) is None


# ── check_de_espuria (inverso de construct: quita «de» con sufijo) ───────────
def test_de_espuria_sufijo_quita_de():
    # אִשְׁתּוֹ SUBS.F.SG.C + sufijo «su» glosado «mujer de» → «mujer» (Gén 25:21)
    r = R.check_de_espuria(hw(strongs='H802', morph='SUBS.F.SG.C', he='אשת',
                              es='mujer de', prs=_prs('su', 'PRS.P3.M.SG')))
    assert r and r[1] == ('set_es', 'mujer', 'mujer de')


def test_de_espuria_del_tambien():
    r = R.check_de_espuria(hw(morph='SUBS.M.SG.C', he='ביתו', es='casa del',
                              prs=_prs('su', 'PRS.P3.M.SG')))
    assert r and r[1] == ('set_es', 'casa', 'casa del')


def test_de_espuria_sin_sufijo_no_toca():
    # sin sufijo pronominal es competencia de check_construct, no de este
    assert R.check_de_espuria(hw(morph='SUBS.F.SG.C', he='אשת', es='mujer de')) is None


def test_de_espuria_sin_de_final_no_toca():
    assert R.check_de_espuria(hw(morph='SUBS.F.SG.C', he='אשת', es='mujer',
                                 prs=_prs('su', 'PRS.P3.M.SG'))) is None


def test_de_espuria_de_suelto_no_toca():
    # «de» sola (una palabra) no se toca: no hay nombre delante
    assert R.check_de_espuria(hw(morph='SUBS.F.SG.C', he='x', es='de',
                                 prs=_prs('su', 'PRS.P3.M.SG'))) is None


def test_de_espuria_locucion_prep_no_toca():
    # לִפְנֵיהֶם «antes de» + posesivo: pide «… de él/ellos», la «de» gobierna al
    # pronombre y NO sobra → no se toca (falso positivo evitado)
    assert R.check_de_espuria(hw(strongs='H6440', morph='SUBS.BOTH.PL.C', he='לפני',
                                 es='antes de', prs=_prs('su', 'PRS.P3.M.PL'))) is None
    assert R.check_de_espuria(hw(morph='SUBS.M.SG.C', he='אחרי', es='después de',
                                 prs=_prs('su', 'PRS.P3.M.SG'))) is None


def test_de_espuria_sufijo_tonico_no_toca():
    # sufijo TÓNICO pospuesto (no posesivo proclítico) → no se toca
    assert R.check_de_espuria(hw(morph='SUBS.F.SG.C', he='x', es='mujer de',
                                 prs=_prs('ellos', 'PRS.P3.M.PL'))) is None


def test_de_espuria_multipalabra_no_toca():
    # gloss multi-palabra queda a reporte (LARGO), no se retoca aquí
    assert R.check_de_espuria(hw(morph='SUBS.F.SG.C', he='x', es='casa grande de',
                                 prs=_prs('su', 'PRS.P3.M.SG'))) is None


# ── check_homograf (autoaplica con --apply) ──────────────────────────────────
def test_homograf_shamah_adv_puso_a_alli():
    r = R.check_homograf(hw(strongs='H8033', morph='ADV', he='שָׁם', es='puso'))
    assert r is not None and r[1] == ('set_es', 'allí', 'puso')


def test_homograf_shamah_direccional_a_alla():
    r = R.check_homograf(hw(strongs='', morph='ADV', he='שָׁמָּה', es='puso'))
    assert r is not None and r[1][1] == 'allá'


def test_homograf_sham_adv_nombre_a_alli():
    # Gén 26:25: ADV שָׁם glosado «nombre» (confusión con SUBS שֵׁם) → «allí»
    # (aunque el Strong quedó mal etiquetado H8034; manda la morfología ADV)
    r = R.check_homograf(hw(strongs='H8034', morph='ADV', he='שָׁם', es='nombre'))
    assert r and r[1] == ('set_es', 'allí', 'nombre')


def test_homograf_sham_adv_nombre_mayuscula():
    r = R.check_homograf(hw(strongs='H8034', morph='ADV', he='שָׁם', es='Nombre'))
    assert r and r[1] == ('set_es', 'Allí', 'Nombre')


def test_homograf_shem_subs_nombre_correcto_no_toca():
    # SUBS שֵׁם glosado «nombre» es CORRECTO → no se toca
    assert R.check_homograf(hw(strongs='H8034', morph='SUBS.M.SG.C',
                               he='שֵׁם', es='nombre')) is None


def test_homograf_shem_subs_a_nombre():
    r = R.check_homograf(hw(strongs='H8034', morph='SUBS.M.SG.C', he='שֵׁם', es='puso'))
    assert r is not None and r[1] == ('set_es', 'nombre', 'puso')


def test_homograf_no_toca_verbo_real():
    # el verbo real שָׂם (H7760) glosado «puso» es CORRECTO → no se marca
    assert R.check_homograf(hw(strongs='H7760', morph='VERBO.QAL.QATAL.P3.M.SG',
                               he='שָׂם', es='puso')) is None


# ── את H853 (acusativo) glosado «con» → «a + tónico» (confusión con H854) ─────
def test_homograf_at_h853_con_a_tonico():
    r = R.check_homograf(hw(strongs='H853', morph='PART', he='אֹתָהּ', es='con',
                            prs={'es': 'ella', 'he_morph': 'PRS.P3.F.SG'}))
    assert r and r[1] == ('idiom', 'a ella', 'con')


def test_homograf_at_h853_pronombre_lo_fija_morfologia():
    # el sufijo es basura («y») pero la MORFOLOGÍA manda → «a él»
    r = R.check_homograf(hw(strongs='H853', morph='PART', he='אֹתוֹ', es='con',
                            prs={'es': 'y', 'he_morph': 'PRS.P3.M.SG'}))
    assert r and r[1] == ('idiom', 'a él', 'con')


def test_homograf_at_h853_plural_a_ellos():
    r = R.check_homograf(hw(strongs='H853', morph='PART', he='אֹתָם', es='con',
                            prs={'es': 'ellos', 'he_morph': 'PRS.P3.M.PL'}))
    assert r and r[1] == ('idiom', 'a ellos', 'con')


def test_homograf_at_h853_sin_sufijo_no_toca():
    assert R.check_homograf(hw(strongs='H853', morph='PART', he='אֵת', es='con')) is None


def test_homograf_at_h853_ya_correcto_no_toca():
    # ya «a ella» (head != «con») → no se toca
    assert R.check_homograf(hw(strongs='H853', morph='PART', he='אֹתָהּ', es='a',
                               prs={'es': 'ella', 'he_morph': 'PRS.P3.F.SG'})) is None


def test_sintaxis_at_h853_defiere_a_homograf():
    # con HOMOGRAF autofixeando, check_sintaxis NO vuelve a reportarlo
    out = R.check_sintaxis(hw(strongs='H853', morph='PART', he='אֹתָהּ', es='con',
                              prs={'es': 'ella', 'he_morph': 'PRS.P3.F.SG'}))
    assert all('objeto directo' not in det for det, _ in out)


def test_homograf_no_pisa_variante_adverbial_valida():
    # «allá»/«donde» son lecturas válidas del adverbio → no se tocan
    assert R.check_homograf(hw(strongs='H8033', morph='ADV', he='שָׁם', es='allá')) is None


# ── check_morfo · verbo finito glosado como infinitivo ──────────────────────
def test_morfo_finito_glosado_infinitivo_bajar():
    r = R.check_morfo(hw(strongs='H3381', morph='VERBO.HIF.WAYYIQT.P3.F.SG',
                         he='תֹּרֶד', es='bajar'))
    assert any('infinitivo' in x and 'bajó' in x for x in r)


def test_morfo_finito_infinitivo_con_enclitico():
    # «beber» (raíz) es infinitivo en morf finita → detectado con sugerencia «bebió»
    r = R.check_morfo(hw(strongs='H8248', morph='VERBO.HIF.WAYYIQT.P3.F.SG',
                         he='תַּשְׁקֵ', es='beber'))
    assert any('infinitivo' in x and 'bebió' in x for x in r)


def test_morfo_infinitivo_enclitico_pegado_hacerlo():
    # enclítico pegado: «hacerlo» → revela «hacer», sugiere irregular «hizo»
    r = R.check_morfo(hw(strongs='H6213', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                         he='יַּעַשׂ', es='hacerlo'))
    assert any('infinitivo' in x and 'hizo' in x for x in r)


def test_tiempo_autofix_qal_ar():
    # QAL WAYYIQT 3sg «edificar» → autofix «edificó»
    r = R.check_tiempo_finito(hw(strongs='H1129', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                 he='יִּבֶן', es='edificar'))
    assert r and r[1] == ('set_es', 'edificó', 'edificar')


def test_tiempo_autofix_qal_irregular_venir():
    r = R.check_tiempo_finito(hw(morph='VERBO.QAL.QATAL.P3.M.PL', he='x', es='venir'))
    assert r and r[1] == ('set_es', 'vinieron', 'venir')


def test_tiempo_no_autofix_hifil():
    # HIF causativo NO se auto-aplica (sentido: «beber»→«dar de beber»)
    assert R.check_tiempo_finito(hw(morph='VERBO.HIF.WAYYIQT.P3.F.SG', he='x',
                                    es='beber')) is None


def test_tiempo_no_autofix_reflexivo():
    # reflexivo «levantarse» NO se auto-aplica (perdería «se»)
    assert R.check_tiempo_finito(hw(morph='VERBO.QAL.WAYYIQT.P3.F.SG', he='x',
                                    es='levantarse')) is None


def test_tiempo_no_autofix_enclitico():
    assert R.check_tiempo_finito(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                    es='hacerlo')) is None


def test_tiempo_no_autofix_no_tercera_persona():
    assert R.check_tiempo_finito(hw(morph='VERBO.QAL.QATAL.P1.COMMON.SG', he='x',
                                    es='hablar')) is None


def test_morfo_infinitivo_morf_no_finita_ok():
    # morfología de INFINITIVO (INFC) glosada como infinitivo → NO se marca
    r = R.check_morfo(hw(strongs='H8248', morph='VERBO.HIF.INFC',
                         he='הַשְׁקוֹת', es='beber'))
    assert not any('infinitivo' in x for x in r)


# ── check_morfo (d) · pronombre sujeto que no concuerda con la morfología ─────
def test_morfo_pronombre_sujeto_singular_en_verbo_plural():
    # Gén 26:8: אָרְכוּ P3.COMMON.PL glosado «después que él estuvo» (él = 3ª sg)
    r = R.check_morfo(hw(strongs='H748', morph='VERBO.QAL.QATAL.P3.COMMON.PL',
                         he='אָרְכוּ', es='después que él estuvo'))
    assert any('pronombre sujeto' in x and 'él' in x for x in r)


def test_morfo_pronombre_sujeto_concuerda_no_marca():
    # «él dijo» en un verbo 3ª sg → concuerda → no se marca
    r = R.check_morfo(hw(strongs='H559', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                         he='יֹּאמֶר', es='él dijo'))
    assert not any('pronombre sujeto' in x for x in r)


def test_morfo_pronombre_sujeto_plural_concuerda_no_marca():
    # «ellos dijeron» en verbo 3ª pl → concuerda
    r = R.check_morfo(hw(strongs='H559', morph='VERBO.QAL.WAYYIQT.P3.M.PL',
                         he='יֹּאמְרוּ', es='ellos dijeron'))
    assert not any('pronombre sujeto' in x for x in r)


def test_morfo_pronombre_oblicuo_tras_preposicion_no_marca():
    # «a él» tras preposición es objeto oblicuo, NO sujeto → no se marca
    r = R.check_morfo(hw(strongs='H5414', morph='VERBO.QAL.WAYYIQT.P3.M.PL',
                         he='יִּתְּנוּ', es='dieron a él'))
    assert not any('pronombre sujeto' in x for x in r)


def test_morfo_pronombre_persona_no_concuerda():
    # «yo» (1ª) en un verbo de 3ª → desajuste de persona
    r = R.check_morfo(hw(strongs='H559', morph='VERBO.QAL.QATAL.P3.M.SG',
                         he='אָמַר', es='yo dije'))
    assert any('pronombre sujeto' in x and 'yo' in x for x in r)


# ── check_morfo · tiempo (WAYYIQT = pretérito, no futuro) ─────────────────────
def test_morfo_wayyiqtol_futuro_flagged():
    r = R.check_morfo(hw(strongs='H6965', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                         he='יָּקָם', es='se levantará'))
    assert any('FUTURO' in x for x in r)


def test_morfo_wayyiqtol_pasado_ok():
    r = R.check_morfo(hw(strongs='H6965', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                         he='יָּקָם', es='se levantó'))
    assert not any('FUTURO' in x for x in r)


def test_morfo_weqatal_futuro_no_flagged():
    # weqatal (SEQ.PERF) sí admite lectura futura/modal → no se marca
    r = R.check_morfo(hw(strongs='H6965', morph='VERBO.QAL.SEQ.PERF.P3.M.SG',
                         he='וְקָם', es='se levantará'))
    assert not any('FUTURO' in x for x in r)


# ── check_morfo · tiempo simétrico (IMPF/yiqtol ≠ pretérito indefinido) ──────
def test_morfo_impf_preterito_sg_flagged():
    # yiqtol glosado como pretérito puntual (-ó) → se marca (debe ir futuro/modal)
    r = R.check_morfo(hw(strongs='H1696', morph='VERBO.PIEL.IMPF.P3.M.SG',
                         he='יְדַבֵּר', es='habló'))
    assert any('PRETÉRITO' in x for x in r)


def test_morfo_impf_preterito_pl_flagged():
    r = R.check_morfo(hw(strongs='H1696', morph='VERBO.PIEL.IMPF.P3.M.PL',
                         he='יְדַבְּרוּ', es='hablaron'))
    assert any('PRETÉRITO' in x for x in r)


def test_morfo_impf_futuro_ok():
    # yiqtol en futuro = lectura correcta → NO se marca
    r = R.check_morfo(hw(strongs='H1696', morph='VERBO.PIEL.IMPF.P3.M.SG',
                         he='יְדַבֵּר', es='hablará'))
    assert not any('PRETÉRITO' in x for x in r)


def test_morfo_impf_imperfecto_habitual_ok():
    # yiqtol como imperfecto habitual español (-aba/-ía) = lectura válida → NO marca
    r = R.check_morfo(hw(strongs='H5927', morph='VERBO.QAL.IMPF.P3.M.SG',
                         he='יַעֲלֶה', es='subía'))
    assert not any('PRETÉRITO' in x for x in r)


def test_morfo_impf_presente_ok():
    r = R.check_morfo(hw(strongs='H1696', morph='VERBO.PIEL.IMPF.P3.M.SG',
                         he='יְדַבֵּר', es='habla'))
    assert not any('PRETÉRITO' in x for x in r)


def test_morfo_seq_imperfecto_preterito_no_flagged():
    # weyiqtol/consecutivo (SEQ) queda excluido del chequeo simétrico
    r = R.check_morfo(hw(strongs='H1696', morph='VERBO.PIEL.SEQ.IMPF.P3.M.SG',
                         he='וִידַבֵּר', es='habló'))
    assert not any('PRETÉRITO' in x for x in r)


# ── check_morfo · volitivos (JUSS/COHORT ≠ pretérito indefinido) ────────────
def test_morfo_jussive_preterito_flagged():
    r = R.check_morfo(hw(strongs='H1961', morph='VERBO.QAL.JUSS.P3.M.SG',
                         he='יְהִי', es='habló'))
    assert any('yusivo' in x for x in r)


def test_morfo_cohortativo_preterito_flagged():
    r = R.check_morfo(hw(strongs='H1980', morph='VERBO.QAL.COHORT.P1.COMMON.PL',
                         he='נֵלְכָה', es='caminaron'))
    assert any('cohortativo' in x for x in r)


def test_morfo_jussive_subjuntivo_ok():
    # yusivo glosado en subjuntivo/imperativo = correcto → NO se marca
    r = R.check_morfo(hw(strongs='H1961', morph='VERBO.QAL.JUSS.P3.M.SG',
                         he='יְהִי', es='sea'))
    assert not any('PRETÉRITO' in x for x in r)


def test_morfo_cohortativo_volitivo_ok():
    r = R.check_morfo(hw(strongs='H1980', morph='VERBO.QAL.COHORT.P1.COMMON.PL',
                         he='נֵלְכָה', es='vamos'))
    assert not any('PRETÉRITO' in x for x in r)


# ── morph_root · morfología compuesta con '+' (#1) ──────────────────────────
def test_morph_root_compuesto_mas():
    assert R.morph_root('PREP+PRS.P1.SG') == 'PREP'
    assert R.morph_root('SUBS.M.SG.C') == 'SUBS'
    assert R.morph_root('VERBO.QAL.WAYYIQT.P3.M.SG') == 'VERBO'


# ── motor hebreo · morph_pos_root NEG ya no cae en SUBS (#5) ─────────────────
def test_morph_pos_root_neg_no_es_subs():
    import morph_validate_utils as MV
    assert MV.morph_pos_root('NEG') == 'NEG'
    # no regresión: sustantivos con código N siguen resolviendo a SUBS
    assert MV.morph_pos_root('NC') == 'SUBS'
    assert MV.morph_pos_root('NPROP') == 'NPROP'
    assert MV.morph_pos_root('VERBO.QAL.WAYYIQT.P3.M.SG') == 'VERBO'


# ── is_pron_suffix · sufijos NO pronominales (#4) ───────────────────────────
def test_is_pron_suffix():
    assert R.is_pron_suffix('PRS.P3.M.SG')
    assert R.is_pron_suffix('')            # sin etiqueta: no bloquea
    assert not R.is_pron_suffix('SUF')
    assert not R.is_pron_suffix('SUF.PARAG.HE')
    assert not R.is_pron_suffix('SUF.PARAG.NUN')
    assert not R.is_pron_suffix('PART')


def test_poses_sufijo_paragogico_no_marca():
    # sufijo paragógico/locativo (no pronominal): no hay posesivo que apilar
    r = R.check_poses(hw(morph='SUBS.F.SG.A', es='su tierra',
                         prs={'he_form': 'ה', 'he_morph': 'SUF.PARAG.HE',
                              'es': 'su'}))
    assert r is None


def test_poses_sufijo_pronominal_sigue_marcando():
    # control: con sufijo PRONOMINAL el apilamiento SÍ se detecta (no regresión)
    r = R.check_poses(hw(morph='SUBS.M.SG.C', es='mío señor',
                         prs={'he_form': 'י', 'he_morph': 'PRS.P1.COMMON.SG',
                              'es': 'mi'}))
    assert r is not None


def test_eufonia_y_ante_hi_a_e():
    r = R.check_eufonia(hw(he='יַּעַשׂ', es='hizo', prefix_es=['y']))
    assert r and r[0][1] == 'e'


def test_eufonia_y_ante_i_a_e():
    r = R.check_eufonia(hw(he='x', es='Israel', prefix_es=['y']))
    assert r and r[0][1] == 'e'


def test_eufonia_y_ante_hie_se_queda():
    # «hielo/hierba» = diptongo /je/ → sigue «y»
    assert R.check_eufonia(hw(es='hierba', prefix_es=['y'])) == []


def test_eufonia_y_normal_no_cambia():
    assert R.check_eufonia(hw(es='casa', prefix_es=['y'])) == []


def test_eufonia_e_mal_aplicada_a_y():
    # «e» ante palabra que no empieza por i → corrige a «y»
    r = R.check_eufonia(hw(es='casa', prefix_es=['e']))
    assert r and r[0][1] == 'y'


def test_eufonia_y_ante_articulo_el_no_cambia():
    # «y el ...»: la palabra siguiente es el prefijo «el», no la raíz
    assert R.check_eufonia(hw(es='hijo', prefix_es=['y', 'el'])) == []


# ── VAV (vav consecutivo de wayyiqtol = «y», nunca «para que») ───────────────
def test_vav_wayyiqtol_para_que_a_y():
    # Gén 25:22: vav consecutivo glosado «para que» → «y»
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.HITPOLEL.WAYYIQT.P3.M.PL',
                                 he='יִּתְרֹצֲצוּ', es='luchaban',
                                 prefix_es=['para que'], prefix_morphs=['CONJ']))
    assert r == [(0, 'para que')]


def test_vav_wayyiqtol_para_a_y():
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                 es='dijo', prefix_es=['para'],
                                 prefix_morphs=['CONJ']))
    assert r == [(0, 'para')]


def test_vav_no_wayyiqtol_no_toca():
    # cohortativo con «para que» es propósito legítimo → no se toca
    assert R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.COHO.P1.COMMON.PL', he='x',
                                    es='sacrifiquemos', prefix_es=['para que'],
                                    prefix_morphs=['CONJ'])) == []


def test_vav_wayyiqtol_y_normal_no_toca():
    # el vav ya está bien glosado «y»
    assert R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                    es='dijo', prefix_es=['y'],
                                    prefix_morphs=['CONJ'])) == []


def test_vav_wayyiqtol_prefijo_no_conj_no_toca():
    # el prefijo con «para que» no es CONJ (p.ej. PREP) → no es el vav
    assert R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                    es='dijo', prefix_es=['para que'],
                                    prefix_morphs=['PREP'])) == []


def test_vav_wayyiqtol_que_a_y():
    # Gén 26:7: «que preguntaron» → «y preguntaron»
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.PL',
                                 he='יִּשְׁאֲלוּ', es='preguntaron',
                                 prefix_es=['que'], prefix_morphs=['CONJ']))
    assert r == [(0, 'que')]


def test_vav_wayyiqtol_si_a_y():
    # Gén 27:21: «si dijo» → «y dijo»
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                 es='dijo', prefix_es=['si'], prefix_morphs=['CONJ']))
    assert r == [(0, 'si')]


def test_vav_wayyiqtol_como_a_y():
    # Gén 29:10 (וַיְהִי כַּאֲשֶׁר): el «cuando» lo lleva el término siguiente;
    # el vav «como» → «y»
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='יְהִי',
                                 es='sucedió', prefix_es=['como'],
                                 prefix_morphs=['CONJ']))
    assert r == [(0, 'como')]


def test_vav_wayyiqtol_hasta_que_a_y():
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                 es='dijo', prefix_es=['hasta que'],
                                 prefix_morphs=['CONJ']))
    assert r == [(0, 'hasta que')]


def test_vav_wayyiqtol_corrupcion_posesiva_a_y():
    # Gén 29:13: vav glosado «su» (corrupción del build) → «y besó»
    r = R.check_vav_wayyiqtol(hw(morph='VERBO.PIEL.WAYYIQT.P3.M.SG', he='יְנַשֶּׁק',
                                 es='besó', prefix_es=['su'], prefix_morphs=['CONJ']))
    assert r == [(0, 'su')]


def test_vav_wayyiqtol_e_eufonica_no_toca():
    # «e» eufónica ya es correcta
    assert R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                    es='fue', prefix_es=['e'],
                                    prefix_morphs=['CONJ'])) == []


def test_vav_wayyiqtol_vacio_no_toca():
    # prefijo CONJ vacío → lo maneja otra pasada, no lo fuerza VAV
    assert R.check_vav_wayyiqtol(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG', he='x',
                                    es='dijo', prefix_es=[''],
                                    prefix_morphs=['CONJ'])) == []


# ── KI (כִּי nunca es la copulativa «y»; default «que») ──────────────────────
def test_ki_stem_y_a_que():
    # Gén 26:7: כִּי glosado «y» → default «que»
    r = R.check_ki(hw(strongs='H3588', morph='CONJ', he='כִּי', es='y'))
    assert len(r) == 1
    det, sug, fld = r[0]
    assert sug == ('set_es', 'que', 'y') and fld == 'es'


def test_ki_por_esqueleto_sin_strong():
    # detecta por esqueleto 'כי' aunque el Strong esté vacío
    r = R.check_ki(hw(strongs='', morph='CONJ', he='כִּי', es='y'))
    assert r and r[0][1] == ('set_es', 'que', 'y')


def test_ki_prefijo_y_espuria_sin_vav():
    # es correcto «que» pero con «y» espuria en prefijo y forma SIN vav → quitar
    r = R.check_ki(hw(strongs='H3588', morph='CONJ', he='כִּי', es='que',
                      prefix_es=['y'], prefix_morphs=['CONJ']))
    assert len(r) == 1
    det, sug, fld = r[0]
    assert sug == ('pfx_set', 0, '', 'y')


def test_ki_con_vav_real_no_toca_prefijo():
    # וְכִי: la grafía SÍ trae vav → el «y» del prefijo es legítimo, no se toca
    r = R.check_ki(hw(strongs='H3588', morph='CONJ', he='וְכִי', es='que',
                      prefix_es=['y'], prefix_morphs=['CONJ']))
    assert r == []


def test_ki_stem_y_mas_prefijo_y():
    # Gén 33:11: es='y' Y prefijo 'y' (sin vav) → dos correcciones
    r = R.check_ki(hw(strongs='H3588', morph='CONJ', he='כִי', es='y',
                      prefix_es=['y'], prefix_morphs=['CONJ']))
    sugs = [x[1] for x in r]
    assert ('pfx_set', 0, '', 'y') in sugs
    assert ('set_es', 'que', 'y') in sugs


def test_ki_es_correcto_no_marca():
    assert R.check_ki(hw(strongs='H3588', morph='CONJ', he='כִּי', es='porque')) == []
    assert R.check_ki(hw(strongs='H3588', morph='CONJ', he='כִּי', es='que')) == []


def test_ki_no_es_ki_no_marca():
    # otra palabra glosada «y» (waw real) no es asunto de KI
    assert R.check_ki(hw(strongs='H2050', morph='CONJ', he='וְ', es='y')) == []


# ── PEN (פֶּן nunca es la copulativa «y»; default «no sea que») ──────────────
def test_pen_stem_y_a_no_sea_que():
    # Gén 26:9/31:24/38:11…: פֶּן glosado «y» → default «no sea que»
    r = R.check_pen(hw(strongs='H6435', morph='CONJ', he='פֶּן', es='y'))
    assert len(r) == 1
    det, sug, fld = r[0]
    assert sug == ('set_es', 'no sea que', 'y') and fld == 'es'


def test_pen_por_esqueleto_sin_strong():
    # detecta por esqueleto 'פן' aunque el Strong esté vacío
    r = R.check_pen(hw(strongs='', morph='CONJ', he='פֶּן', es='y'))
    assert r and r[0][1] == ('set_es', 'no sea que', 'y')


def test_pen_prefijo_y_espuria_sin_vav():
    # es correcto pero con «y» espuria en prefijo y forma SIN vav → quitar
    r = R.check_pen(hw(strongs='H6435', morph='CONJ', he='פֶּן', es='no sea que',
                       prefix_es=['y'], prefix_morphs=['CONJ']))
    assert len(r) == 1
    assert r[0][1] == ('pfx_set', 0, '', 'y')


def test_pen_es_correcto_no_marca():
    # las lecturas legítimas no se tocan
    assert R.check_pen(hw(strongs='H6435', morph='CONJ', he='פֶּן', es='no sea que')) == []
    assert R.check_pen(hw(strongs='H6435', morph='CONJ', he='פֶּן', es='para que')) == []
    assert R.check_pen(hw(strongs='H6435', morph='CONJ', he='פֶּן', es='quizá')) == []


def test_pen_no_es_pen_no_marca():
    # otra palabra glosada «y» (waw real) no es asunto de PEN
    assert R.check_pen(hw(strongs='H2050', morph='CONJ', he='וְ', es='y')) == []


# ── CONTAGIO (glosa copiada del vecino; REPORTE puro) ───────────────────────
def test_contagio_detecta_bleed_saltando_particula():
    # 47:14: שֶׁבֶר «grano» quedó «tierra», contagiado de אֶרֶץ, con partícula en medio
    flat = [
        (0, 0, hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אֶרֶץ', es='tierra')),
        (1, 0, hw(strongs='', morph='PART', he='אֵת', es='')),
        (2, 0, hw(strongs='H7668', morph='SUBS.M.SG.A', he='שֶׁבֶר', es='tierra')),
    ]
    r = R.check_contagio(flat)
    assert len(r) == 1 and r[0][0] == 2 and r[0][1] == 0


def test_contagio_mismo_esqueleto_no_marca():
    # repetición hebrea real (misma forma) → NO es contagio
    flat = [
        (0, 0, hw(strongs='H122', morph='ADJ.M.SG.A', he='אָדֹם', es='rojo')),
        (1, 0, hw(strongs='', morph='ADJ.M.SG.A', he='אָדֹם', es='rojo')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_mismo_strong_no_marca():
    # misma palabra (mismo Strong) glosada igual → legítimo
    flat = [
        (0, 0, hw(strongs='H6754', morph='SUBS.M.SG.C', he='צֶלֶם', es='imagen')),
        (1, 0, hw(strongs='H6754', morph='SUBS.M.SG.C', he='צַלְמ', es='imagen')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_es_distinta_no_marca():
    flat = [
        (0, 0, hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אֶרֶץ', es='tierra')),
        (1, 0, hw(strongs='H7668', morph='SUBS.M.SG.A', he='שֶׁבֶר', es='grano')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_numeral_stoplist_no_marca():
    # numerales recurren de forma legítima → excluidos aunque difieran Strong/forma
    flat = [
        (0, 0, hw(strongs='H8147', morph='SUBS.M.DU.A', he='שְׁנַיִם', es='dos')),
        (1, 0, hw(strongs='H8145', morph='ADJ.M.SG.A', he='שֵׁנִי', es='dos')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_misma_raiz_final_no_marca():
    # שֵׁם / שְׁמִ = misma raíz שם (forma final ם vs medial מ) → NO es contagio
    flat = [
        (0, 0, hw(strongs='H8034', morph='SUBS.M.SG.C', he='שֵׁם', es='nombre')),
        (1, 0, hw(strongs='', morph='SUBS.M.SG.C', he='שְׁמִ', es='nombre')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_misma_raiz_afijo_no_marca():
    # צֶלֶם / צַלְמ = misma raíz צלם con afijo → NO es contagio
    flat = [
        (0, 0, hw(strongs='H6754', morph='SUBS.M.SG.C', he='צֶלֶם', es='imagen')),
        (1, 0, hw(strongs='', morph='SUBS.M.SG.C', he='צַלְמ', es='imagen')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_nprop_no_marca():
    flat = [
        (0, 0, hw(strongs='H3130', morph='NPROP', he='יוסף', es='Yosef')),
        (1, 0, hw(strongs='H3128', morph='NPROP', he='יהוסף', es='Yosef')),
    ]
    assert R.check_contagio(flat) == []


def test_contagio_sin_estadistica_solo_reporte():
    # sin estadística no se puede VERIFICAR el lexema → solo reporte (suggest None)
    save = R.estilo_usuario
    R.estilo_usuario = None
    try:
        flat = [
            (0, 0, hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אֶרֶץ', es='tierra')),
            (1, 0, hw(strongs='H7668', morph='SUBS.M.SG.A', he='שֶׁבֶר', es='tierra')),
        ]
        r = R.check_contagio(flat)
        assert len(r) == 1 and r[0][5] is None
    finally:
        R.estilo_usuario = save


def test_contagio_verbo_nunca_autofix():
    # un VERBO contagiado se REPORTA (el tiempo/lexema lo elige el usuario), nunca
    # autofix — determinista: VERBO no está en el set NOMINAL de restauración
    flat = [
        (0, 0, hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אֶרֶץ', es='tierra')),
        (1, 0, hw(strongs='H1980', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                  he='יֵּלֶךְ', es='tierra')),
    ]
    r = R.check_contagio(flat)
    assert len(r) == 1 and r[0][5] is None


def test_contagio_autofix_verificado_por_strong():
    # con estadística: SUBS H802 contagiado «tierra» → autofix a «mujer» (preferida)
    if R.estilo_usuario is None:
        return
    flat = [
        (0, 0, hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אֶרֶץ', es='tierra')),
        (1, 0, hw(strongs='H802', morph='SUBS.F.SG.C', he='אשת', es='tierra')),
    ]
    r = R.check_contagio(flat)
    assert len(r) == 1
    sug = r[0][5]
    assert sug and sug[0] == 'set_es' and sug[1] == 'mujer' and sug[2] == 'tierra'


def test_contagio_glosa_conocida_no_marca():
    # «mujer» ES glosa conocida-correcta de H802 → no es contagio → no se marca
    if R.estilo_usuario is None:
        return
    flat = [
        (0, 0, hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אֶרֶץ', es='mujer')),
        (1, 0, hw(strongs='H802', morph='SUBS.F.SG.C', he='אשת', es='mujer')),
    ]
    assert R.check_contagio(flat) == []


# ── ENCLIT (clítico objeto antepuesto a verbo no-finito → enclítico) ─────────
def test_enclit_infinitivo_clitico_antepuesto():
    # «la llorar» (INFC) → sugiere «llorarla»
    r = R.check_enclit(hw(morph='VERBO.QAL.INFC', he='x', es='la llorar'))
    assert r and r[1] == 'llorarla'


def test_enclit_imperativo_clitico_antepuesto():
    # Gén 25:30: «me alimenta» (HIF.IMPV + sufijo objeto) → enclítico (reporte)
    r = R.check_enclit(hw(morph='VERBO.HIF.IMPV.P2.M.SG', he='הַלְעִיטֵנִי',
                          es='me alimenta'))
    assert r and 'imperativo' in r[0].lower() and 'alimentame' in r[0]
    assert 'acentuación' in r[0]
    assert r[1] is None   # report-only (acentuación requiere criterio)


def test_enclit_imperativo_se_lo_deja_reflex():
    # el clítico «se» se deja a REFLEX (verbos pronominales)
    assert R.check_enclit(hw(morph='VERBO.QAL.IMPV.P2.M.SG', he='x',
                             es='se inclina')) is None


def test_enclit_articulo_mas_sustantivo_no_marca():
    # «la mujer» NO es clítico+verbo (morfología no verbal) → no se marca
    assert R.check_enclit(hw(morph='SUBS.F.SG.A', he='x', es='la mujer')) is None


def test_enclit_imperativo_ya_enclitico_no_marca():
    # forma ya enclítica de una sola palabra → no dispara
    assert R.check_enclit(hw(morph='VERBO.HIF.IMPV.P2.M.SG', he='x',
                             es='aliméntame')) is None


def test_puntocoma_subs_autofix():
    # sustantivo con arrastre → recupera el segmento bueno (autofix)
    r = R.check_puntocoma(hw(morph='SUBS.M.PL.C', he='x', es='sus hermanos; y'))
    assert r and r[1] == ('set_es', 'sus hermanos', 'sus hermanos; y')


def test_puntocoma_strip_conjuncion_inicial():
    # verbo con «que» arrastrado al inicio → se limpia a «conocido»
    r = R.check_puntocoma(hw(morph='VERBO.QAL.QATAL.P3.M.SG', he='x',
                             es='que conocido; la cual'))
    assert r and r[1] == ('set_es', 'conocido', 'que conocido; la cual')


def test_puntocoma_verbo_pronombre_solo_reporte():
    # VERBO reducido a pronombre → ambiguo: reporte (suggest=None), no autofix
    r = R.check_puntocoma(hw(morph='VERBO.QAL.QATAL.P3.COMMON.PL', he='x',
                             es='nosotros; pero enseñoreado'))
    assert r and r[1] is None


def test_puntocoma_sin_punto_y_coma_ok():
    assert R.check_puntocoma(hw(morph='SUBS.M.SG.A', he='x', es='casa')) is None


# ── check_poses: posesivo tónico/largo incrustado en la raíz ────────────────
def _prs(es, morph='PRS.P1.COMMON.SG'):
    return {'es': es, 'he_morph': morph, 'gr_word': '', 'strongs': ''}


def test_poses_tonico_incrustado_mio_senor():
    # «mío señor» + sufijo «mi» → doble «mi mío señor»: quitar el tónico de la raíz
    r = R.check_poses(hw(strongs='H113', morph='SUBS.M.SG.C', he='אֲדֹנִי',
                         es='mío señor', prs=_prs('mi')))
    assert r and r[1] == ('set_es', 'señor', 'mío señor')


def test_poses_tonico_plural_mios_hijos():
    r = R.check_poses(hw(morph='SUBS.M.PL.C', he='x', es='míos hijos',
                         prs=_prs('mis', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('set_es', 'hijos', 'míos hijos')


def test_poses_largo_nuestro_senor():
    # forma larga «nuestro» con sufijo «mi» (1sg, hebreo אֲדֹנִי) → quitar
    r = R.check_poses(hw(morph='SUBS.M.SG.C', he='אֲדֹנִי', es='nuestro señor',
                         prs=_prs('mi')))
    assert r and r[1] == ('set_es', 'señor', 'nuestro señor')


def test_poses_tonico_solo_sin_sustantivo_reporte():
    # raíz = solo «suya» (falta el sustantivo) → reporte, no autofix
    r = R.check_poses(hw(morph='SUBS.F.SG.C', he='x', es='suya',
                         prs=_prs('su', 'PRS.P3.F.SG')))
    assert r and r[1] is None


def test_poses_no_toca_atono_normal():
    # «su» átono no está en LONG_POSS: no lo toca esta rama (dedup lo maneja el visor)
    r = R.check_poses(hw(morph='SUBS.F.SG.C', he='x', es='su casa',
                         prs=_prs('su', 'PRS.P3.F.SG')))
    # no debe sugerir quitar «su» de la raíz como si fuera tónico
    assert not (r and r[1] and r[1][0] == 'set_es' and r[1][1] == 'casa')


def test_conjuga_salan_a_salen():
    r = R.check_conjuga(hw(strongs='H3318', morph='VERBO.QAL.PTCA.F.PL',
                          he='יֹצְאֹת', es='salan'))
    assert r and r[1] == ('set_es', 'salen', 'salan')


def test_conjuga_no_toca_no_verbo():
    assert R.check_conjuga(hw(morph='SUBS.M.SG.A', he='x', es='salan')) is None


def test_recorrido_verbo_glosado_por():
    # infinitivo glosado como preposición suelta «por» → recorrido
    r = R.check_morph_mismatch(hw(strongs='H7579', morph='VERBO.QAL.INFC',
                                  he='שְׁאֹב', es='por'))
    assert r and 'recorrido' in r.lower()


def test_recorrido_verbo_glosado_normal_ok():
    # un verbo con glosa léxica normal no se marca
    r = R.check_morph_mismatch(hw(strongs='H7579', morph='VERBO.QAL.INFC',
                                  he='שְׁאֹב', es='sacar'))
    assert not (r and 'recorrido' in (r or '').lower())


def test_mismatch_barak_hifil_bendecir():
    # ברך en Hifil = «hacer arrodillar», no bendecir/amparar
    r = R.check_morph_mismatch(hw(strongs='H1288', morph='VERBO.HIF.WAYYIQT.P3.M.SG',
                                  he='יַּבְרֵךְ', es='amparó'))
    assert r and 'arrodillar' in r


def test_mismatch_barak_piel_bendecir_ok():
    # el Piel SÍ es bendecir → no se marca
    r = R.check_morph_mismatch(hw(strongs='H1288', morph='VERBO.PIEL.WAYYIQT.P3.M.SG',
                                  he='יְבָרֶךְ', es='bendijo'))
    assert not (r and 'arrodillar' in (r or ''))


# ── INFINITIVO hebreo glosado como sustantivo derivado (שקה «abrevadero») ────
def test_inf_sustantivo_derivado_abrevadero():
    # INFC glosado con un sustantivo derivado (-ero) en vez del verbo → reporte
    r = R.check_morph_mismatch(hw(strongs='H8248', morph='VERBO.HIF.INFC',
                                  he='הַשְׁקֹת', es='abrevadero'))
    assert r and 'infinitivo' in r.lower() and 'derivado' in r.lower()


def test_inf_clitic_antepuesto_mas_sustantivo():
    # clítico antepuesto en la raíz + sustantivo derivado («lo abrevadero») → reporte
    r = R.check_morph_mismatch(hw(strongs='H8248', morph='VERBO.HIF.INFC',
                                  he='הַשְׁקֹת', es='lo abrevadero'))
    assert r and 'infinitivo' in r.lower()


def test_inf_verbo_correcto_no_marca():
    # infinitivo español válido → NO se marca
    assert R.check_morph_mismatch(hw(strongs='H8248', morph='VERBO.HIF.INFC',
                                     he='הַשְׁקֹת', es='abrevar')) is None
    assert R.check_morph_mismatch(hw(strongs='H8248', morph='VERBO.HIF.INFC',
                                     he='הַשְׁקֹת', es='beber')) is None


def test_inf_finito_o_gerundio_no_marca():
    # verbo finito o gerundio (uso legítimo INF→verbo) → NO se marca (no es sufijo nominal)
    assert R.check_morph_mismatch(hw(morph='VERBO.HIF.INFC', he='x', es='abrevó')) is None
    assert R.check_morph_mismatch(hw(morph='VERBO.QAL.INFC', he='x', es='durmiendo')) is None


def test_inf_recorrido_funcional_sigue_siendo_recorrido():
    # «por» sobre un INFC se marca como RECORRIDO (no como sustantivo derivado)
    r = R.check_morph_mismatch(hw(strongs='H7579', morph='VERBO.QAL.INFC',
                                  he='שְׁאֹב', es='por'))
    assert r and 'recorrido' in r.lower()


# ── check_morph_mismatch · SUBS/ADJ glosado como VERBO conjugado (Gén 24:22) ──
def test_mismatch_subs_verbo_conjugado_imperfecto():
    # מִשְׁקָל SUBS «peso» glosado «pesaban» (imperfecto) → reporte
    r = R.check_morph_mismatch(hw(strongs='H4948', morph='SUBS.M.SG.C',
                                  he='מִשְׁקָל', es='pesaban'))
    assert r and 'verbo conjugado' in r.lower()


def test_mismatch_subs_verbo_conjugado_preterito():
    r = R.check_morph_mismatch(hw(strongs='H4948', morph='SUBS.M.SG.C',
                                  he='מִשְׁקָל', es='pesó'))
    assert r and 'verbo conjugado' in r.lower()


def test_mismatch_subs_posesivo_mas_verbo():
    # con posesivo antepuesto se ignora el «su» y se mira el núcleo verbal
    r = R.check_morph_mismatch(hw(strongs='H4948', morph='SUBS.M.SG.C',
                                  he='מִשְׁקָל', es='su pesaban'))
    assert r and 'verbo conjugado' in r.lower()


def test_mismatch_subs_correcto_no_marca():
    # el sustantivo correcto (con o sin posesivo) NO se marca
    assert R.check_morph_mismatch(hw(strongs='H4948', morph='SUBS.M.SG.C',
                                     he='מִשְׁקָל', es='su peso')) is None
    assert R.check_morph_mismatch(hw(strongs='H4948', morph='SUBS.M.SG.C',
                                     he='מִשְׁקָל', es='peso')) is None


def test_mismatch_subs_clitico_reflexivo_mas_verbo():
    # קֶרֶב SUBS «interior» glosado «se aproximó»: salta el clítico «se» y ve el verbo
    r = R.check_morph_mismatch(hw(strongs='H7130', morph='SUBS.M.SG.C',
                                  he='קֶרֶב', es='se aproximó'))
    assert r and 'verbo conjugado' in r.lower()


def test_mismatch_subs_clitico_me_nos_mas_verbo():
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.C', he='x', es='me guardó'))
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.C', he='x', es='nos hablaron'))


def test_mismatch_subs_clitico_solo_no_marca():
    # solo el clítico sin verbo detrás no debe marcar (no hay núcleo verbal)
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.C', he='x', es='se')) is None


def test_mismatch_subs_infinitivo_nominalizado_ok():
    # nominalización legítima de infinitivo («el andar», «poder») → NO se marca
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.A', he='x', es='andar')) is None
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.A', he='x', es='el poder')) is None


def test_mismatch_subs_terminacion_ambigua_no_marca():
    # sustantivos con final NO verbal inequívoco no se marcan (razón, canción, casa)
    assert R.check_morph_mismatch(hw(morph='SUBS.F.SG.A', he='x', es='razón')) is None
    assert R.check_morph_mismatch(hw(morph='SUBS.F.SG.A', he='x', es='canción')) is None
    assert R.check_morph_mismatch(hw(morph='SUBS.F.SG.A', he='x', es='casa')) is None


def test_mismatch_subs_transliteracion_no_marca():
    # transliteración (es_source «translit_*»): «nafshó» (נפש) NO es verbo → no marca
    h = hw(strongs='H5315', morph='SUBS.BOTH.SG.C', he='נַפְשׁ', es='nafshó')
    h['es_source'] = 'translit_nefesh'
    assert R.check_morph_mismatch(h) is None


def test_mismatch_subs_no_verbo_lookalike_no_marca():
    # «triste» (adjetivo, termina en -iste) NO se marca
    assert R.check_morph_mismatch(hw(morph='ADJ.M.SG.A', he='x', es='triste')) is None


def test_mismatch_subs_adverbio_ras_no_marca():
    # «atrás»/«detrás» (adverbio, -rás): el check no usa el futuro → no marca
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.A', he='x', es='atrás')) is None
    assert R.check_morph_mismatch(hw(morph='SUBS.M.SG.A', he='x', es='detrás')) is None


def test_morfo_futuro_irregular_flagged():
    # futuros irregulares (dirá, pondrá, será) también se cazan por la «r»
    for g in ('dirá', 'pondrá', 'será', 'dirán'):
        r = R.check_morfo(hw(strongs='H1', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                             he='יֹּאמֶר', es=g))
        assert any('FUTURO' in x for x in r), g


# ── check_peninsular (autoaplica con --apply) ────────────────────────────────
def test_peninsular_limpio_no_marca():
    assert R.check_peninsular(hw(es='casa buena')) == []


def test_peninsular_coherente_con_latam():
    # test robusto: el hallazgo debe coincidir EXACTO con to_latam_neutral,
    # sea cual sea la regla concreta (si el conversor no cambia nada, no marca).
    src = 'vosotros multiplicaos'
    esperado = R.to_latam_neutral(src)
    out = R.check_peninsular(hw(es=src))
    if esperado.strip() != src.strip():
        assert out and out[0] == ('es', None, src, esperado)
    else:
        assert out == []


# ── check_concord: número con género desconocido (Gén 23:17 «los árbol») ─────
def test_concord_numero_articulo_plural_nombre_singular():
    # «los árbol»: género desconocido (termina en consonante) pero número discrepa
    out = R.check_concord(hw(strongs='H6086', morph='SUBS.M.SG.A', he='עֵץ',
                             es='árbol', prefix_es=['los']))
    assert out and out[0][1] == ('pfx_set', 0, 'el', 'los')


def test_concord_numero_articulo_singular_nombre_plural():
    out = R.check_concord(hw(strongs='H6086', morph='SUBS.M.PL.A', he='עֵצִים',
                             es='árboles', prefix_es=['el']))
    assert out and out[0][1] == ('pfx_set', 0, 'los', 'el')


def test_concord_numero_valido_no_marca():
    assert R.check_concord(hw(strongs='H6086', morph='SUBS.M.SG.A', he='עֵץ',
                              es='árbol', prefix_es=['el'])) == []


# ── CONCORD demostrativo suelto vs sustantivo referente (Gén 25:17) ──────────
def _run_concord(*hws, ch=25, vs=17):
    d = {'verses': [verse(ch, vs, *hws)]}
    findings, _, _, _ = R.run(d, '__test__', ((ch, 1), (ch, 999)),
                              ((1, 1), (1, 999)), 2, {'CONCORD'})
    demo = [f for f in findings if 'demostrativo' in f.detail]
    return d, findings, demo


def test_concord_demostrativo_suelto_genero_vecino():
    # אֵלֶּה PRON.DEM.COMMON.PL «estas» + «años» (masc) → «estos» (Gén 25:17)
    d, findings, demo = _run_concord(
        hw(strongs='H428', morph='PRON.DEM.COMMON.PL', he='אֵלֶּה', es='estas'),
        hw(strongs='H8141', morph='ADJ.M.DU.C', he='שְׁנֵי', es='años de'))
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'estos', 'estas')
    R.apply_safe(d, findings, slug='__test__')
    assert d['verses'][0]['pairs'][0]['he_words'][0]['es'] == 'estos'


def test_concord_demostrativo_femenino_vecino():
    # «estos casas» → «estas» (referente femenino)
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אלה', es='estos'),
        hw(morph='SUBS.F.PL.A', he='x', es='casas'))
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'estas', 'estos')


def test_concord_demostrativo_ya_concuerda_no_toca():
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אלה', es='estos'),
        hw(morph='SUBS.M.PL.A', he='x', es='años'))
    assert demo == []


def test_concord_demostrativo_neutro_no_toca():
    # neutros (esto/eso/aquello) no concuerdan en género → no se tocan
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.SG', he='זה', es='esto'),
        hw(morph='SUBS.M.SG.A', he='x', es='libro'))
    assert demo == []


def test_concord_demostrativo_referente_ambiguo_no_toca():
    # referente de género desconocido (consonante final) → no autofix
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אלה', es='estas'),
        hw(morph='SUBS.M.PL.A', he='x', es='árboles'))
    # «árboles»→«árbol» termina en consonante → es_gender None → sin certeza
    assert demo == []


def test_concord_demostrativo_conserva_mayuscula():
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אלה', es='Estas'),
        hw(morph='ADJ.M.DU.C', he='x', es='años'))
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'Estos', 'Estas')


def test_concord_demostrativo_salta_copula_pronombre():
    # «estas [son] hijos» → «estos»: el enlazador הֵם «son» (PRON) se salta y el
    # referente es «hijos» (masc). Reproduce Gén 25:16 p0 (que quedaba sin tocar).
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אֵלֶּה', es='estas'),
        hw(morph='PRON.PERS.P3.M.PL', he='הֵם', es='son'),
        hw(strongs='H1121', morph='SUBS.M.PL.C', he='בְּנֵי', es='hijos de'))
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'estos', 'estas')


def test_concord_demostrativo_referente_con_posesivo_en_raiz():
    # referente cuya glosa arranca con posesivo: «sus hijos» → cabeza «hijos»
    # (masc, género seguro) → «estos». (Salto de posesivo/artículo inicial.)
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אֵלֶּה', es='estas'),
        hw(strongs='H1121', morph='SUBS.M.PL.C', he='בְּנֵיהֶם', es='sus hijos'))
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'estos', 'estas')


def test_concord_demostrativo_atributivo_usa_anterior_ignora_siguiente():
    # ATRIBUTIVO «tierra esta» (זֹאת): el referente es el sustantivo ANTERIOR
    # («tierra», fem) → «esta» correcta; el sustantivo SIGUIENTE masc («rio») NO
    # debe arrastrarla a «este». Guarda de Gén 15:18.
    _d, _f, demo = _run_concord(
        hw(strongs='H776', morph='SUBS.BOTH.SG.A', he='אָרֶץ', es='tierra'),
        hw(morph='PRON.DEM.F.SG', he='זֹּאת', es='esta'),
        hw(strongs='H5104', morph='SUBS.M.SG.C', he='נְּהַר', es='rio'))
    assert demo == []


def test_concord_demostrativo_atributivo_corrige_desde_referente_es():
    # ATRIBUTIVO «tierra este» → «esta»: género tomado del referente ESPAÑOL
    # anterior («tierra» fem), aunque el hebreo del sustantivo fuera masc.
    _d, _f, demo = _run_concord(
        hw(strongs='H776', morph='SUBS.M.SG.A', he='אֶרֶץ', es='tierra'),
        hw(morph='PRON.DEM.M.SG', he='זֶה', es='este'))
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'esta', 'este')


def test_concord_demostrativo_corta_en_verbo_finito():
    # verbo finito entre demostrativo y sustantivo → frontera de cláusula: no cruza,
    # no hay referente seguro adelante → no toca.
    _d, _f, demo = _run_concord(
        hw(morph='PRON.DEM.COMMON.PL', he='אלה', es='estas'),
        hw(morph='VERBO.QAL.WAYYIQT.P3.M.PL', he='x', es='dijeron'),
        hw(morph='SUBS.M.PL.A', he='y', es='años'))
    assert demo == []


# ── demostrativo PENTATEUCAL הַהוּא/הַהִוא (etiquetado PRON.PERS, no DEM) ───────
def test_concord_demostrativo_pentateucal_pron_pers_corrige():
    # ATRIBUTIVO «tierra aquel»: הִוא es PRON.PERS.P3.F.SG (pentateucal) pero
    # acompaña «tierra» (fem esp.) → «aquella» (Gén 2:12).
    _d, _f, demo = _run_concord(
        hw(strongs='H776', morph='SUBS.M.SG.A', he='אֶרֶץ', es='tierra'),
        hw(strongs='H1931', morph='PRON.PERS.P3.F.SG', he='הִוא', es='aquel'),
        ch=2, vs=12)
    assert len(demo) == 1 and demo[0].suggest == ('set_es', 'aquella', 'aquel')


def test_concord_demostrativo_pron_pers_noche_no_rompe():
    # «noche aquella»: הוּא masc en hebreo, pero «noche» es fem esp. → «aquella»
    # YA es correcta → NO se toca (guarda de Gén 19:33/26:24).
    _d, _f, demo = _run_concord(
        hw(strongs='H3915', morph='SUBS.M.SG.A', he='לַיְלָה', es='noche'),
        hw(strongs='H1931', morph='PRON.PERS.P3.M.SG', he='הוּא', es='aquella'),
        ch=19, vs=33)
    assert demo == []


def test_concord_demostrativo_pron_pers_ano_no_rompe():
    # «año aquel»: הִוא fem en hebreo, pero «año» es masc esp. → «aquel» YA es
    # correcta → NO se toca (guarda de Gén 47:17, שנה fem hebreo vs año masc).
    _d, _f, demo = _run_concord(
        hw(strongs='H8141', morph='SUBS.F.SG.A', he='שָׁנָה', es='año'),
        hw(strongs='H1931', morph='PRON.PERS.P3.F.SG', he='הִוא', es='aquel'),
        ch=47, vs=17)
    assert demo == []


def test_concord_demostrativo_pron_pers_copulativo_no_toca():
    # COPULATIVO «Kena'an, esta [es] Bet-El»: el token anterior es NOMBRE PROPIO
    # (no atributivo) → PRON.PERS no se corrige (evita falso «este», Gén 35:6).
    _d, _f, demo = _run_concord(
        hw(strongs='H3667', morph='NPROP', he='כְּנַעַן', es='Kena'),
        hw(strongs='H1931', morph='PRON.PERS.P3.F.SG', he='הִוא', es='esta'),
        hw(strongs='H1008', morph='NPROP', he='בֵּית־אֵל', es='Beit-El'),
        ch=35, vs=6)
    assert demo == []


def test_concord_invariable_en_s_no_falso_positivo():
    # «los análisis» (invariable) NO debe marcarse por número
    assert R.check_concord(hw(morph='SUBS.M.SG.A', he='X',
                              es='análisis', prefix_es=['los'])) == []


# ── LARGO: 3+ palabras en un token (raíz+sufijo) ─────────────────────────────
def test_largo_su_el_pies():
    # Gén 24:32: raíz «él pies» + suf «su» → render «su él pies» (3 palabras)
    tok = hw(strongs='H7272', morph='SUBS.F.DU.C', he='רַגְלָיו', es='él pies',
             prs={'he_morph': 'PRS.P3.M.SG', 'es': 'su'})
    assert R.check_largo(tok)


def test_largo_perifrasis_dio_a_luz_ok():
    assert R.check_largo(hw(strongs='H3205', morph='VERBO.QAL.QATAL.P3.F.SG',
                            he='יָלְדָה', es='dio a luz')) is None


def test_largo_perifrasis_peso_de_honra_ok():
    assert R.check_largo(hw(strongs='H3519', morph='SUBS.M.SG.A',
                            he='כָּבוֹד', es='peso de honra')) is None


def test_largo_sus_pies_dos_palabras_ok():
    # 2 palabras (sufijo + lexema) es lo normal → no marca
    tok = hw(strongs='H7272', morph='SUBS.F.DU.C', he='רַגְלָיו', es='pies',
             prs={'he_morph': 'PRS.P3.M.SG', 'es': 'sus'})
    assert R.check_largo(tok) is None


def test_largo_prefijos_no_cuentan():
    # «y la tierra» = prefijos + 1 lexema: NO es LARGO
    tok = hw(strongs='H776', morph='SUBS.F.SG.A', he='אֶרֶץ', es='tierra',
             prefix_es=['y', 'la'])
    assert R.check_largo(tok) is None


def test_largo_arrastre_cuatro_palabras():
    assert R.check_largo(hw(morph='SUBS.M.SG.C', he='X',
                            es='ellos porción la comida de'))


def test_largo_pasar_la_noche_ok():
    assert R.check_largo(hw(morph='VERBO.QAL.INFC', he='לִין',
                            es='pasar la noche')) is None


# ── CANON: build_canon + run + apply_safe ────────────────────────────────────
def test_build_canon_unanime():
    d = {'verses': [
        verse(1, 1, hw(es='lugar')),
        verse(1, 2, hw(es='lugar')),
        verse(1, 3, hw(es='lugar')),
    ]}
    canon = R.build_canon(d, (1, 1), (1, 999), 2)
    k = R.canon_key(hw(es='lugar'))
    assert canon.get(k) == 'lugar'


def test_build_canon_polisemia_excluida():
    # misma clave con DOS sentidos distintos en el libro → excluida del canon
    d = {'verses': [
        verse(1, 1, hw(es='lugar')),
        verse(1, 2, hw(es='lugar')),
        verse(3, 1, hw(es='orilla')),   # fuera del rango fuente, pero en el libro
    ]}
    canon = R.build_canon(d, (1, 1), (1, 999), 2)
    k = R.canon_key(hw(es='lugar'))
    assert k not in canon


def test_build_canon_numero_no_es_polisemia():
    # «lugar»/«lugares» = solo número → NO cuenta como polisemia (es_norm)
    d = {'verses': [
        verse(1, 1, hw(es='lugar')),
        verse(1, 2, hw(es='lugar')),
        verse(2, 1, hw(es='lugares')),
    ]}
    canon = R.build_canon(d, (1, 1), (1, 999), 2)
    k = R.canon_key(hw(es='lugar'))
    assert canon.get(k) == 'lugar'


def test_default_canon_source_to_ultimo_cerrado():
    d = {'verses': [
        verse(26, 1, hw()),
        verse(26, 35, hw()),
        verse(27, 1, hw()),
    ]}
    assert R.last_verse_of_chapter(d, 26) == 35
    assert R.default_canon_source_to('genesis', d, locked={1, 22, 26}) == '26:35'
    assert R.default_canon_source_to('genesis', d, locked=set()) == '1:0'


def test_run_canon_flag_y_apply():
    d = {'verses': [
        verse(1, 1, hw(es='lugar')),
        verse(1, 2, hw(es='lugar')),
        verse(1, 3, hw(es='lugar')),
        verse(2, 1, hw(es='lugares')),   # objetivo: número distinto → CANON
    ]}
    findings, canon, _, _ = R.run(
        d, '__test__', ((2, 1), (2, 999)), ((1, 1), (1, 999)), 2, {'CANON'})
    canon_f = [f for f in findings if f.cat == 'CANON']
    assert len(canon_f) == 1
    f = canon_f[0]
    assert f.vs == 1 and f.suggest[0] == 'set_es' and f.suggest[1] == 'lugar'
    # aplicar y verificar que escribe la glosa canónica
    n = R.apply_safe(d, findings, slug='__test__')
    assert n == 1
    tok = d['verses'][3]['pairs'][0]['he_words'][0]
    assert tok['es'] == 'lugar'


def test_run_canon_no_flag_si_polisemico():
    d = {'verses': [
        verse(1, 1, hw(es='lugar')),
        verse(1, 2, hw(es='lugar')),
        verse(3, 1, hw(es='orilla')),        # hace la clave polisémica
        verse(2, 1, hw(es='lugares')),
    ]}
    findings, _, _, _ = R.run(
        d, '__test__', ((2, 1), (2, 999)), ((1, 1), (1, 999)), 2, {'CANON'})
    assert [f for f in findings if f.cat == 'CANON'] == []


# ── estilo_usuario.sugerir_ctx (desambiguación por contexto) ─────────────────
def test_sugerir_ctx_desambigua_por_vecino():
    import estilo_usuario as EU
    prev_cache = EU._cache
    EU._cache = {'H999': {'formas': {'PREP': {
        'total': 10, 'preferida': 'a', 'pct': 50.0, 'ambigua': True,
        'glosas': [{'es': 'a', 'n': 5, 'pct': 50.0},
                   {'es': 'hacia', 'n': 5, 'pct': 50.0}],
        'ctx': {'prev': {}, 'next': {'מקום': {'es': 'hacia', 'pct': 80.0, 'n': 4}}},
    }}}}
    try:
        r = EU.sugerir_ctx('H999', 'PREP', 'a', next_ck='מקום')
        assert r and r['sugerida'] == 'hacia' and 'next' in r['ctx']
        # ya coincide con tu uso en ese contexto → no sugiere
        assert EU.sugerir_ctx('H999', 'PREP', 'hacia', next_ck='מקום') is None
        # contexto desconocido → no sugiere
        assert EU.sugerir_ctx('H999', 'PREP', 'a', next_ck='zzz') is None
        # forma NO ambigua → no aplica contexto
        EU._cache['H999']['formas']['PREP']['ambigua'] = False
        assert EU.sugerir_ctx('H999', 'PREP', 'a', next_ck='מקום') is None
    finally:
        EU._cache = prev_cache


# ── finding_to_dict (export) ─────────────────────────────────────────────────
def test_finding_to_dict_serializable():
    import json
    f = R.F('CONSTRUCT', 23, 1, 1, 0, 'בְנֵי', 'SUBS.M.PL.C', 'detalle',
            suggest=('set_es', 'hijos de', 'hijos'), field='es', protected=False)
    dd = R.finding_to_dict(f)
    assert dd['cat'] == 'CONSTRUCT' and dd['autofix'] is True
    assert dd['suggest'][1] == 'hijos de'
    json.dumps(dd, ensure_ascii=False)   # no debe lanzar


# ── BUG2 + R8: check_poses número/persona (el sufijo hebreo manda) ───────────
def test_poses_bug2_numero_mi_a_nuestro():
    # raíz «mi padre» (1ª SG) + sufijo hebreo P1.PL «nuestro» → «nuestro padre»
    r = R.check_poses(hw(morph='SUBS.M.SG.C', he='אבינו', es='mi padre',
                         prs=_prs('nuestro', 'PRS.P1.COMMON.PL')))
    assert r and r[1] == ('poss_rehome', 'mi padre', 'nuestro padre', 'nuestro')


def test_poses_bug2_numero_plural_concuerda():
    # raíz «mis hijos» (1ª SG) + sufijo P1.PL → «nuestros hijos» (plural masc.)
    r = R.check_poses(hw(morph='SUBS.M.PL.C', he='בנינו', es='mis hijos',
                         prs=_prs('nuestro', 'PRS.P1.COMMON.PL')))
    assert r and r[1] == ('poss_rehome', 'mis hijos', 'nuestros hijos', 'nuestro')


def test_poses_r8_persona_su_mi_padre():
    # raíz «mi padre» (1ª) + sufijo P3.SG «su» → «su padre» (sufijo manda)
    r = R.check_poses(hw(morph='SUBS.M.SG.C', he='אביו', es='mi padre',
                         prs=_prs('su', 'PRS.P3.M.SG')))
    assert r and r[1] == ('poss_rehome', 'mi padre', 'su padre', 'su')


def test_poses_redundante_3a_intacto():
    # «sus ovejas» + sufijo P3.SG «su» → SIGUE limpiando el sufijo (sin cambios)
    r = R.check_poses(hw(morph='SUBS.F.PL.C', he='צאנו', es='sus ovejas',
                         prs=_prs('su', 'PRS.P3.M.SG')))
    assert r and r[1] == ('clear_prs', 'su')


def test_poses_rehome_apply_end_to_end():
    # run + apply_safe: «mi padre»+P1.PL → escribe «nuestro padre» y limpia sufijo
    d = {'verses': [verse(31, 1, hw(morph='SUBS.M.SG.C', he='אבינו',
                                    es='mi padre',
                                    prs=_prs('nuestro', 'PRS.P1.COMMON.PL')))]}
    findings, _, _, _ = R.run(d, '__test__', ((31, 1), (31, 999)),
                              ((1, 1), (1, 999)), 2, {'POSES'})
    n = R.apply_safe(d, findings, slug='__test__')
    tok = d['verses'][0]['pairs'][0]['he_words'][0]
    assert n == 1 and tok['es'] == 'nuestro padre'
    assert (tok['prs_suffix'].get('es') or '') == ''


# ── R11: PRON nunca sobre VERBO ──────────────────────────────────────────────
def test_pron_no_toca_verbo():
    r = R.check_pron(hw(morph='VERBO.QAL.INFC', he='תתי', es='a ella',
                        prs=_prs('la', 'PRS.P3.F.SG')))
    assert r == []


def test_pron_prep_si_despoja():
    r = R.check_pron(hw(morph='PREP', he='אליה', es='a ella',
                        prs=_prs('la', 'PRS.P3.F.SG')))
    assert any(s and s[0] == 'set_es' for _d, s in r)


# ── R1: RECORRIDO omite repetición hebrea real (mismo esqueleto) ─────────────
def test_recorrido_omite_repeticion_hebrea_real():
    d = {'verses': [{'chapter': 26, 'verse': 28, 'pairs': [{'he_words': [
        hw(strongs='', morph='PREP', he='בֵּין', es='entre'),
        hw(strongs='', morph='PREP', he='בֵּין', es='entre'),
    ]}]}]}
    findings, _, _, _ = R.run(d, '__test__', ((26, 1), (26, 999)),
                              ((1, 1), (1, 999)), 2, {'RECORRIDO'})
    assert [f for f in findings if f.cat == 'RECORRIDO'] == []


def test_recorrido_marca_si_esqueleto_distinto():
    d = {'verses': [{'chapter': 26, 'verse': 1, 'pairs': [{'he_words': [
        hw(strongs='', morph='SUBS.M.SG.A', he='מֶלֶךְ', es='rey'),
        hw(strongs='', morph='SUBS.M.SG.A', he='אֶרֶץ', es='rey'),
    ]}]}]}
    findings, _, _, _ = R.run(d, '__test__', ((26, 1), (26, 999)),
                              ((1, 1), (1, 999)), 2, {'RECORRIDO'})
    assert [f for f in findings if f.cat == 'RECORRIDO']


# ── construct-guard: no añade «de» a glosa adverbial/verbal ──────────────────
def test_construct_no_de_sobre_adverbio():
    prev = R.estilo_usuario
    R.estilo_usuario = None
    try:
        assert R.check_construct(hw(morph='SUBS.F.SG.C', he='עֵת',
                                    es='todavía')) is None
    finally:
        R.estilo_usuario = prev


def test_construct_no_de_sobre_verbo():
    prev = R.estilo_usuario
    R.estilo_usuario = None
    try:
        assert R.check_construct(hw(morph='SUBS.F.DU.C', he='עֵינֵי',
                                    es='parecían')) is None
    finally:
        R.estilo_usuario = prev


# ── R13: verbo de parto ילד glosado «luz» → «dio a luz» ──────────────────────
def test_parto_luz_wayyiqtol_a_dio_a_luz():
    r = R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.WAYYIQT.P3.F.SG',
                            he='תֵּלֶד', es='luz'))
    assert r and r[1] == ('set_es', 'dio a luz', 'luz')


def test_parto_luz_infinitivo():
    r = R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.INFC',
                            he='לֶדֶת', es='luz'))
    assert r and r[1][1] == 'dar a luz'


def test_parto_luz_infc_sin_strong_ledet():
    # לִדְתָּהּ inf. constructo de ילד (yod inicial cae → empieza en ל), SIN strong:
    # esqueleto לדת debe reconocerse como parto → «dar a luz» (Gén 38:5/38:27)
    r = R.check_homograf(hw(strongs='', morph='VERBO.QAL.INFC',
                            he='לִדְתָּ', es='luz'))
    assert r and r[1] == ('set_es', 'dar a luz', 'luz')


def test_parto_no_toca_luz_sustantivo():
    # אוֹר «luz» sustantivo real (no verbo de parto) → no se toca
    assert R.check_homograf(hw(strongs='H216', morph='SUBS.F.SG.A',
                               he='אוֹר', es='luz')) is None


# ── ילד TRUNCADO al verbo «dar» suelto → locución completa (Gén 24:24) ───────
def test_parto_dar_truncado_dio_qatal():
    # יָלְדָה QATAL fem sg glosado «dio» (truncado) → «dio a luz»
    r = R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.QATAL.P3.F.SG',
                            he='יָלְדָה', es='dio'))
    assert r and r[1] == ('set_es', 'dio a luz', 'dio')


def test_parto_dar_truncado_dieron_plural():
    r = R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.QATAL.P3.F.PL',
                            he='יָלְדוּ', es='dieron'))
    assert r and r[1] == ('set_es', 'dieron a luz', 'dieron')


def test_parto_dar_truncado_futuro():
    r = R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.IMPF.P3.F.SG',
                            he='תֵּלֵד', es='dará'))
    assert r and r[1] == ('set_es', 'dará a luz', 'dará')


def test_parto_dar_truncado_con_a():
    # fragmento «dio a» (sin «luz») también se completa
    r = R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.QATAL.P3.F.SG',
                            he='יָלְדָה', es='dio a'))
    assert r and r[1] == ('set_es', 'dio a luz', 'dio a')


def test_parto_dar_completo_no_se_retoca():
    # ya correcto «dio a luz» → NO se vuelve a tocar
    assert R.check_homograf(hw(strongs='H3205', morph='VERBO.QAL.QATAL.P3.F.SG',
                               he='יָלְדָה', es='dio a luz')) is None


def test_parto_dar_no_toca_natan_real():
    # el verbo נתן «dar» real (H5414, NO ילד) glosado «dio» → no se toca
    assert R.check_homograf(hw(strongs='H5414', morph='VERBO.QAL.QATAL.P3.M.SG',
                               he='נָתַן', es='dio')) is None


# ── R5: preposición עם «pueblo» → «con» ──────────────────────────────────────
def test_prep_im_pueblo_a_con():
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִם', es='pueblo'))
    assert r and r[1] == ('set_es', 'con', 'pueblo')


def test_prep_im_pueblo_con_pronombre():
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִמּוֹ',
                            es='pueblo él'))
    assert r and r[1] == ('set_es', 'con él', 'pueblo él')


def test_prep_im_fusion_contigo():
    # עם + sufijo «ti» → «contigo» (fija raíz y limpia sufijo)
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִמָּךְ',
                            es='pueblo', prs=_prs('ti', 'PRS.P2.F.SG')))
    assert r and r[1] == ('idiom', 'contigo', 'pueblo')


def test_prep_im_reconstruye_con_el_desde_morfologia():
    # עם + sufijo 3ms → «con él» reconstruido de la morfología (limpia sufijo)
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִמּוֹ',
                            es='pueblo', prs=_prs('él', 'PRS.P3.M.SG')))
    assert r and r[1] == ('idiom', 'con él', 'pueblo')


def test_prep_im_sufijo_posesivo_su_se_corrige():
    # BUG «su con» (×8 corpus): sufijo 3ms guardado como posesivo «su» → «con él»
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִמּוֹ',
                            es='pueblo', prs=_prs('su', 'PRS.P3.M.SG')))
    assert r and r[1] == ('idiom', 'con él', 'pueblo')


def test_prep_im_nosotros_gen2425():
    # Gén 24:25 «pueblo nosotros» → «con nosotros»
    r = R.check_homograf(hw(strongs='', morph='PREP', he='עִמָּנוּ',
                            es='pueblo', prs=_prs('nosotros', 'PRS.P1.COMMON.PL')))
    assert r and r[1] == ('idiom', 'con nosotros', 'pueblo')


def test_prep_im_conmigo_desde_morfologia():
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִמִּי',
                            es='pueblo', prs=_prs('a mí', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'conmigo', 'pueblo')


# ── FUSIÓN conmigo/contigo cuando la raíz YA es «con» (Gén 26:3/26:24) ───────
def test_prep_im_con_mas_te_a_contigo():
    # Gén 26:3 עִמְּךָ: raíz «con» + sufijo «te» (2ms) render «te con» → «contigo»
    r = R.check_homograf(hw(strongs='', morph='PREP', he='עִמְּ',
                            es='con', prs=_prs('te', 'PRS.P2.M.SG')))
    assert r and r[1] == ('idiom', 'contigo', 'con')


def test_prep_et_con_mas_ti_a_contigo():
    # Gén 26:24 אִתְּךָ: raíz «con» + «ti» render «con ti» → «contigo»
    r = R.check_homograf(hw(strongs='', morph='PREP', he='אִתְּ',
                            es='con', prs=_prs('ti', 'PRS.P2.M.SG')))
    assert r and r[1] == ('idiom', 'contigo', 'con')


def test_prep_im_con_mas_mi_a_conmigo():
    r = R.check_homograf(hw(strongs='', morph='PREP', he='עִמִּ',
                            es='con', prs=_prs('mí', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'conmigo', 'con')


def test_prep_im_con_el_no_toca():
    # 3ª persona: «con él» ya correcto → NO se toca (evita no-op destructivo)
    assert R.check_homograf(hw(strongs='', morph='PREP', he='עִמּ',
                               es='con', prs=_prs('él', 'PRS.P3.M.SG'))) is None


def test_prep_im_con_nosotros_no_toca():
    assert R.check_homograf(hw(strongs='', morph='PREP', he='עִמָּ', es='con',
                               prs=_prs('nosotros', 'PRS.P1.COMMON.PL'))) is None


def test_prep_im_contigo_ya_no_toca():
    assert R.check_homograf(hw(strongs='', morph='PREP', he='עִמָּ', es='contigo',
                               prs=_prs('', 'PRS.P2.F.SG'))) is None


def test_prep_im_de_con_nosotros_prefijo_conservado():
    # מֵעִם: prefijo «de» + «con nosotros» — la fusión NO aplica (3/pl) → None,
    # el prefijo se conserva (no se compara contra el render con prefijo)
    h = hw(strongs='', morph='PREP', he='עִמָּ', es='con',
           prs=_prs('nosotros', 'PRS.P1.COMMON.PL'))
    h['prefix_es'] = ['de']
    assert R.check_homograf(h) is None


# ── MORFO · participio con objeto sobre verbo finito activo (Gén 26:15/26:29) ─
def test_morfo_participio_con_objeto_plural():
    r = R.check_morfo(hw(strongs='', morph='VERBO.PIEL.QATAL.P3.COMMON.PL',
                         he='סִתְּמוּ', es='cegado', prs=_prs('los', 'PRS.P3.M.PL')))
    assert r and any('PARTICIPIO' in x and 'cegaron' in x for x in r)


def test_morfo_participio_con_objeto_1pl():
    r = R.check_morfo(hw(strongs='', morph='VERBO.QAL.QATAL.P1.COMMON.PL',
                         he='נגענו', es='tocado', prs=_prs('te', 'PRS.P2.M.SG')))
    assert r and any('PARTICIPIO' in x and 'tocamos' in x for x in r)


def test_morfo_participio_sin_objeto_no_marca():
    # participio SIN objeto (perfecto/adjetival legítimo: «hemos hallado») → no marca
    assert R.check_morfo(hw(strongs='', morph='VERBO.QAL.QATAL.P1.COMMON.PL',
                            he='מצאנו', es='hallado')) == []


def test_morfo_participio_pasivo_no_marca():
    # binyan pasivo (NIF) con objeto → no se marca (lectura participial defendible)
    assert R.check_morfo(hw(strongs='', morph='VERBO.NIF.QATAL.P3.M.SG',
                            he='x', es='ungido', prs=_prs('te', 'PRS.P2.M.SG'))) == []


# ── GLOSAFUNC · lexema de contenido glosado como palabra funcional ───────────
def test_glosafunc_limpia_helper():
    assert R._glosafunc_limpia('mujer')
    assert R._glosafunc_limpia('hermano')
    assert not R._glosafunc_limpia('hijo de')     # multipalabra
    assert not R._glosafunc_limpia('su nombre')
    assert not R._glosafunc_limpia('y')            # funcional
    assert not R._glosafunc_limpia('a')            # <2 letras


def test_glosafunc_autofix_mujer():
    # SUBS.F.SG.C H802 glosado «y» → restaura «mujer» (preferida por-forma)
    r = R.check_glosafunc(hw(strongs='H802', morph='SUBS.F.SG.C', he='אשת', es='y'))
    assert r and r[1] and r[1][0] == 'set_es'
    assert r[1][1] == 'mujer' and r[1][2] == 'y'


def test_glosafunc_autofix_padre():
    r = R.check_glosafunc(hw(strongs='H1', morph='SUBS.M.SG.C', he='אב', es='y'))
    assert r and r[1] and r[1][0] == 'set_es' and R._glosafunc_limpia(r[1][1])


def test_glosafunc_multiword_a_reporte():
    # H1121 preferida «hijo de» (multipalabra) → NO autofix, reporte con candidato
    r = R.check_glosafunc(hw(strongs='H1121', morph='SUBS.M.SG.C', he='בן', es='y'))
    assert r and r[1] is None and 'hijo de' in r[0]


def test_glosafunc_numeral_no_marca():
    # «un» NO está en el set funcional (numeral H259 legítimo) → no se toca
    assert R.check_glosafunc(hw(strongs='H259', morph='ADJ.M.SG.A', he='אחד', es='un')) is None


def test_glosafunc_contenido_valido_no_marca():
    assert R.check_glosafunc(hw(strongs='H802', morph='SUBS.F.SG.C', he='אשת', es='mujer')) is None


def test_glosafunc_no_content_morph_no_marca():
    # PREP glosada «de» es normal, no es un lexema de contenido → no se marca
    assert R.check_glosafunc(hw(strongs='H4480', morph='PREP', he='מן', es='de')) is None


def test_glosafunc_verbo_no_autofix_reporte():
    # VERBO glosado funcional: se REPORTA pero NO se autofixea (tiempo/persona lo
    # decides tú). Sin Strong ni esqueleto con datos → reporte sin candidato.
    r = R.check_glosafunc(hw(strongs='', morph='VERBO.QAL.QATAL.P3.M.SG',
                             he='', es='que'))
    assert r and r[1] is None


# ── GLOSAFUNC (sufijo) · posesivo glosado como palabra funcional (Gén 27:13) ──
def test_suf_func_su_desde_morfologia():
    # אִמּוֹ: SUBS.F.SG + sufijo PRS.P3.M.SG glosado «y» → «su» (render «su madre»)
    r = R.check_suf_func(hw(strongs='H517', morph='SUBS.F.SG.C', he='אם',
                            es='madre', prs=_prs('y', 'PRS.P3.M.SG')))
    assert r and r[1] == ('set_prs', 'su', 'y')


def test_suf_func_mis_plural():
    # sustantivo PLURAL + poseedor 1ª sg → «mis» (concordancia con el poseído)
    r = R.check_suf_func(hw(strongs='', morph='SUBS.M.PL.C', he='בנים',
                            es='hijos', prs=_prs('de', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('set_prs', 'mis', 'de')


def test_suf_func_tu():
    r = R.check_suf_func(hw(strongs='', morph='SUBS.F.SG.C', he='אם',
                            es='madre', prs=_prs('si', 'PRS.P2.M.SG')))
    assert r and r[1] == ('set_prs', 'tu', 'si')


def test_suf_func_ya_posesivo_no_toca():
    # sufijo ya posesivo «su» → lo deja a POSES/CONCORD (no lo pisa)
    assert R.check_suf_func(hw(strongs='', morph='SUBS.F.SG.C', he='אם',
                               es='madre', prs=_prs('su', 'PRS.P3.M.SG'))) is None


def test_suf_func_verbo_no_toca():
    # sufijo PRS sobre VERBO = OBJETO, no posesivo → no se toca
    assert R.check_suf_func(hw(strongs='', morph='VERBO.QAL.QATAL.P3.M.SG',
                               he='x', es='mató', prs=_prs('y', 'PRS.P1.COMMON.SG'))) is None


def test_con_pronombre_helper():
    assert R._con_pronombre('PRS.P1.COMMON.SG') == 'conmigo'
    assert R._con_pronombre('PRS.P2.F.SG') == 'contigo'
    assert R._con_pronombre('PRS.P3.M.SG') == 'con él'
    assert R._con_pronombre('PRS.P3.F.SG') == 'con ella'
    assert R._con_pronombre('PRS.P1.COMMON.PL') == 'con nosotros'
    assert R._con_pronombre('PRS.P2.M.PL') == 'con ustedes'
    assert R._con_pronombre('PRS.P3.M.PL') == 'con ellos'
    assert R._con_pronombre('PRS.P3.F.PL') == 'con ellas'
    assert R._con_pronombre('') is None
    assert R._con_pronombre('SUF.PARAG.HE') is None


def test_prep_im_no_toca_sustantivo_pueblo():
    # עַם sustantivo «pueblo» (SUBS) → legítimo, no se toca
    assert R.check_homograf(hw(strongs='H5971', morph='SUBS.M.SG.A',
                               he='עַם', es='pueblo')) is None


def test_prep_im_parado_conmigo_desde_sufijo_es():
    # עִמָּדִי «conmigo» quedó «parado» (homógrafo עמד); sufijo sin morfología,
    # solo prs_suffix.es «mí» → reconstruye «conmigo» desde la glosa del sufijo
    r = R.check_homograf(hw(strongs='', morph='PREP', he='עִמָּדִי',
                            es='parado', prs=_prs('mí', '')))
    assert r and r[1] == ('idiom', 'conmigo', 'parado')


def test_prep_im_parado_con_nosotros():
    r = R.check_homograf(hw(strongs='', morph='PREP', he='עִמָּדֵנוּ',
                            es='parado', prs=_prs('nosotros', '')))
    assert r and r[1] == ('idiom', 'con nosotros', 'parado')


def test_prep_im_parado_sin_sufijo_solo_con():
    r = R.check_homograf(hw(strongs='H5973', morph='PREP', he='עִם', es='parado'))
    assert r and r[1] == ('set_es', 'con', 'parado')


# ── את (H854) «con»: raíz errónea «y él» → «con él» (vía HOMOGRAF) ────────────
def test_prep_et_y_el_a_con_el():
    r = R.check_homograf(hw(strongs='H854', morph='PREP', he='אִתּוֹ',
                            es='y', prs=_prs('él', 'PRS.P3.M.SG')))
    assert r and r[1] == ('idiom', 'con él', 'y')


def test_prep_et_ya_con_no_toca():
    # «con» ya correcto → no se toca
    assert R.check_homograf(hw(strongs='H854', morph='PREP', he='אִתּוֹ',
                               es='con', prs=_prs('él', 'PRS.P3.M.SG'))) is None


# ── הִנֵּה H2009 «he aquí» (HOMOGRAF, determinista por Strong) ────────────────
def test_hinne_aqui_a_he_aqui():
    r = R.check_homograf(hw(strongs='H2009', morph='PART.DEM', he='הִנֵּה', es='aquí'))
    assert r and r[1] == ('set_es', 'he aquí', 'aquí')


def test_hinne_mayuscula_conserva():
    r = R.check_homograf(hw(strongs='H2009', morph='PART.DEM', he='הִנֵּה', es='Aquí'))
    assert r and r[1] == ('set_es', 'He aquí', 'Aquí')


def test_hinne_ya_he_aqui_no_toca():
    assert R.check_homograf(hw(strongs='H2009', morph='PART.DEM',
                               he='הִנֵּה', es='he aquí')) is None


def test_hinne_con_sufijo_no_toca():
    # הִנֵּנִי «heme aquí» (con sufijo PRS) lo maneja hinneh_idiom, no este bloque
    assert R.check_homograf(hw(strongs='H2009', morph='PART.DEM', he='הִנֵּנִי',
                               es='aquí', prs=_prs('me', 'PRS.P1.COMMON.SG'))) is None


# ── PREPRON: preposición determinista + pronombre reconstruido ───────────────
def test_prepron_el_un_mi_a_a_mi():
    # אֵלַי glosado «un mí» → «a mí» (אל→a determinista)
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלַי',
                             es='un', prs=_prs('mí', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'a mí', 'un')


def test_prepron_el_un_ellos_a_a_ellos():
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֲלֵהֶם',
                             es='un', prs=_prs('ellos', 'PRS.P3.M.PL')))
    assert r and r[1] == ('idiom', 'a ellos', 'un')


def test_prepron_bet_su_ellos_a_en_ellos():
    # בָּהֶם glosado «su ellos» → «en ellos» (ב→en)
    r = R.check_prep_pron(hw(strongs='', morph='PREP', he='בָּהֶם',
                             es='su', prs=_prs('ellos', 'PRS.P3.M.PL')))
    assert r and r[1] == ('idiom', 'en ellos', 'su')


def test_prepron_min_su_ellos_a_de_ellos():
    r = R.check_prep_pron(hw(strongs='H4480', morph='PREP', he='מֵהֶם',
                             es='su', prs=_prs('ellos', 'PRS.P3.M.PL')))
    assert r and r[1] == ('idiom', 'de ellos', 'su')


def test_prepron_al_sin_sufijo_un_a_a():
    # אֶל־ sin sufijo glosado «un» → «a»
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֶל־', es='un'))
    assert r and r[1] == ('idiom', 'a', 'un')


def test_prepron_lamed_basura_suple_a():
    # ל con raíz BASURA («un») ya NO se deja en reporte: se suple «a» + pronombre
    # (a↔para sigue siendo estilo; el motor nunca deja «un mí»/«un ellos»)
    r = R.check_prep_pron(hw(strongs='', morph='PREP', he='לָהֶם',
                             es='un', prs=_prs('ellos', 'PRS.P3.M.PL')))
    assert r and r[1] == ('idiom', 'a ellos', 'un')


def test_prepron_lamed_un_mi_a_a_mi():
    # לִי «un» + sufijo 1cs → «a mí» (Gén 25:31)
    r = R.check_prep_pron(hw(strongs='', morph='PREP', he='לִי',
                             es='un', prs=_prs('mí', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'a mí', 'un')


def test_prepron_lamed_prep_valida_se_respeta():
    # si la raíz YA es «para» (elección válida), NO se fuerza a «a»: se respeta y
    # solo se reconstruye el pronombre del sufijo (sufijo sin glosa → «para mí»)
    r = R.check_prep_pron(hw(strongs='', morph='PREP', he='לִי',
                             es='para', prs=_prs('', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'para mí', 'para')


def test_prepron_lamed_para_mi_ya_correcto_no_toca():
    # «para» + «mí» ya es correcto → no se toca (no fuerza «a»)
    assert R.check_prep_pron(hw(strongs='', morph='PREP', he='לִי',
                                es='para', prs=_prs('mí', 'PRS.P1.COMMON.SG'))) is None


def test_prepron_pronombre_perdido_a_a_mi():
    # אֵלַי glosado «a» con sufijo PRS sin glosa → «a mí»
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלַי',
                             es='a', prs=_prs('', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'a mí', 'a')


def test_prepron_no_toca_prep_valida_completa():
    # «a él» ya bien formado (raíz «a», sufijo «él») → no se toca
    assert R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלָיו',
                                es='a', prs=_prs('él', 'PRS.P3.M.SG'))) is None


def test_prepron_no_toca_con_via_homograf():
    # עם/את las lleva HOMOGRAF; PREPRON no debe tocarlas
    assert R.check_prep_pron(hw(strongs='H5973', morph='PREP', he='עִמּוֹ',
                                es='y', prs=_prs('él', 'PRS.P3.M.SG'))) is None


def test_prepron_no_toca_subs():
    # solo PREP; un SUBS con «un» no se toca aquí
    assert R.check_prep_pron(hw(strongs='H900001', morph='SUBS.M.SG.A',
                                he='מָקוֹם', es='un lugar')) is None


# ── PREPRON v2: constructo con pronombre DOBLE («a mí él» → «a él») ───────────
def test_prepron_doble_a_mi_el():
    # אֵלָיו: raíz «a mí» (artefacto constructo) + sufijo «él» (real) → «a él»
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלָיו',
                             es='a mí', prs=_prs('él', 'PRS.P3.M.SG')))
    assert r and r[1] == ('idiom', 'a él', 'a mí')


def test_prepron_doble_sobre_mi_ellos():
    r = R.check_prep_pron(hw(strongs='H5921', morph='PREP', he='עֲלֵיהֶם',
                             es='sobre mí', prs=_prs('ellos', 'PRS.P3.M.PL')))
    assert r and r[1] == ('idiom', 'sobre ellos', 'sobre mí')


def test_prepron_doble_a_mi_1sg_sin_sufijo_no_toca():
    # «a mí» 1ª sg SIN sufijo es la glosa correcta → NO se toca
    assert R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלַי',
                                es='a mí')) is None


# ── PREPRON v2: pronombre BASURA («para y» → «para él», respeta «para») ───────
def test_prepron_para_y_a_para_el():
    # ל con raíz VÁLIDA «para» ya elegida → se respeta, solo se arregla el pronombre
    r = R.check_prep_pron(hw(strongs='H7971', morph='PREP', he='לּוֹ',
                             es='para', prs=_prs('y', 'PRS.P3.M.SG')))
    assert r and r[1] == ('idiom', 'para él', 'para')


def test_prepron_a_mi_y_strip_basura():
    # «a mí y» 1ª sg → «a mí» (quita la «y» espuria del sufijo)
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלַי',
                             es='a mí', prs=_prs('y', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'a mí', 'a mí')


# ── PREPRON v2: posesivo proclítico espurio («su en» → «en ellos») ───────────
def test_prepron_posesivo_su_en_ellos():
    r = R.check_prep_pron(hw(strongs='', morph='PREP', he='בָּהֶם',
                             es='en', prs=_prs('su', 'PRS.P3.M.PL')))
    assert r and r[1] == ('idiom', 'en ellos', 'en')


def test_prepron_posesivo_por_mi():
    # בַּעֲדִי «por mí»: raíz «por» + sufijo «mi» (posesivo) → «por mí»
    r = R.check_prep_pron(hw(strongs='', morph='PREP', he='בַּעֲדִי',
                             es='por', prs=_prs('mi', 'PRS.P1.COMMON.SG')))
    assert r and r[1] == ('idiom', 'por mí', 'por')


# ── PREPRON v2: artículo/clítico como raíz («la ella» → «a ella») ────────────
def test_prepron_articulo_la_ella():
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלֶיהָ',
                             es='la', prs=_prs('ella', 'PRS.P3.F.SG')))
    assert r and r[1] == ('idiom', 'a ella', 'la')


def test_prepron_articulo_lo_ti():
    r = R.check_prep_pron(hw(strongs='H413', morph='PREP', he='אֵלֶיךָ',
                             es='lo', prs=_prs('ti', 'PRS.P2.M.SG')))
    assert r and r[1] == ('idiom', 'a ti', 'lo')


def test_prepron_articulo_sin_sufijo_no_toca():
    # «al» sin sufijo pronominal es demasiado contextual → NO se toca
    assert R.check_prep_pron(hw(strongs='H5921', morph='PREP', he='עַל־',
                                es='al')) is None


# ── PREPRON v2: guarda anti-frase legítima ───────────────────────────────────
def test_prepron_no_toca_frase_legitima():
    # «por causa de» (frase, 2ª palabra no es pronombre) → NO se toca
    assert R.check_prep_pron(hw(strongs='', morph='PREP', he='בַּעֲבוּר',
                                es='por causa de')) is None


# ── MORPH_MISMATCH: נגד «saber» → contar/declarar ────────────────────────────
def test_mismatch_nagad_saber():
    r = R.check_morph_mismatch(hw(strongs='H5046', morph='VERBO.HIF.WAYYIQT.P3.F.SG',
                                  he='תַּגֵּד', es='saber'))
    assert r and 'נגד' in r and 'contar' in r


def test_mismatch_nagad_supo_sabido():
    assert R.check_morph_mismatch(hw(strongs='H5046', morph='VERBO.HIF.WAYYIQT.P3.M.PL',
                                     he='יַּגִּידוּ', es='supo'))
    assert R.check_morph_mismatch(hw(strongs='H5046', morph='VERBO.HOF.QATAL.P3.M.SG',
                                     he='הֻגַּד', es='sabido'))


def test_mismatch_nagad_conto_no_marca():
    # ya corregido a «contó» → no se reporta
    r = R.check_morph_mismatch(hw(strongs='H5046', morph='VERBO.HIF.WAYYIQT.P3.F.SG',
                                  he='תַּגֵּד', es='contó'))
    assert not (r and 'נגד' in r)


def test_mismatch_yada_saber_no_marca():
    # ידע H3045 «saber» glosado «supo» es CORRECTO → no debe marcarse
    r = R.check_morph_mismatch(hw(strongs='H3045', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                  he='יֵּדַע', es='supo'))
    assert not (r and 'נגד' in r)


# ── MORPH_MISMATCH: אָחוֹת «hermana» glosada «uno» (report-only) ──────────────
def test_mismatch_ajot_uno_reporta():
    r = R.check_morph_mismatch(hw(strongs='', morph='SUBS.F.SG.C', he='אֲחֹת', es='uno'))
    assert r and 'hermana' in r and 'modismo' in r


def test_mismatch_ajot_una_reporta():
    r = R.check_morph_mismatch(hw(strongs='', morph='SUBS.F.SG.C', he='אֲחוֹת', es='una'))
    assert r and 'hermana' in r


def test_mismatch_ajot_hermana_correcta_no_marca():
    # ya glosada «hermana» → no se reporta por este motivo
    r = R.check_morph_mismatch(hw(strongs='H269', morph='SUBS.F.SG.C',
                                  he='אֲחֹת', es='hermana'))
    assert not (r and 'hermana' in (r or '') and 'אָחוֹת' in (r or ''))


def test_mismatch_ajot_es_report_only():
    # NO debe ser autofix (por el modismo «una a otra»): report-only devuelve str
    r = R.check_morph_mismatch(hw(strongs='', morph='SUBS.F.SG.C', he='אֲחֹת', es='uno'))
    assert isinstance(r, str)


# ── R2: TIEMPOVERBAL amplía a -er/-ir regulares ──────────────────────────────
def test_tiempo_autofix_ir_regular_abrir():
    r = R.check_tiempo_finito(hw(strongs='H6605', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                 he='יִפְתַּח', es='abrir'))
    assert r and r[1] == ('set_es', 'abrió', 'abrir')


def test_tiempo_autofix_er_regular_temer():
    r = R.check_tiempo_finito(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                 he='x', es='temer'))
    assert r and r[1] == ('set_es', 'temió', 'temer')


def test_tiempo_no_autofix_ir_stemchanger():
    # «gemir» eleva la vocal (gimió) → NO autofix (queda en reporte MORFO)
    assert R.check_tiempo_finito(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                    he='x', es='gemir')) is None


def test_tiempo_no_autofix_er_vocalico():
    # «poseer» tallo vocálico (poseyó) → NO autofix
    assert R.check_tiempo_finito(hw(morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                    he='x', es='poseer')) is None


# ── R10: nombre divino en minúscula (report-only) ────────────────────────────
def test_divino_minuscula_reporta():
    r = R.check_morph_mismatch(hw(strongs='H430', morph='SUBS.M.PL.C',
                                  he='אֱלֹהֵי', es='dios de'))
    assert r and 'divino' in r.lower()


def test_divino_mayuscula_no_reporta_por_este_motivo():
    r = R.check_morph_mismatch(hw(strongs='H430', morph='SUBS.M.PL.C',
                                  he='אֱלֹהֵי', es='Dios de'))
    assert not (r and 'divino' in r.lower())


# ── REFLEX: verbos de postración pronominales ───────────────────────────────
def test_reflex_qadad_inclino_3sg():
    # יִּקֹּד H6915 WAYYIQT 3ms «inclinó» → «se inclinó» (Gén 24:26)
    r = R.check_reflexivo(hw(strongs='H6915', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                             he='יִּקֹּד', es='inclinó'))
    assert r and r[1] == ('set_es', 'se inclinó', 'inclinó')


def test_reflex_qadad_incline_1sg():
    # אֶקֹּד H6915 WAYYIQT 1cs «incliné» → «me incliné» (Gén 24:48; el clítico
    # concuerda con la PERSONA del verbo hebreo, no siempre «se»)
    r = R.check_reflexivo(hw(strongs='H6915', morph='VERBO.QAL.WAYYIQT.P1.COMMON.SG',
                             he='אֶקֹּד', es='incliné'))
    assert r and r[1] == ('set_es', 'me incliné', 'incliné')


def test_reflex_shajah_inclinaron_3pl():
    r = R.check_reflexivo(hw(strongs='H7812', morph='VERBO.HIT.WAYYIQT.P3.M.PL',
                             he='יִּשְׁתַּחֲווּ', es='inclinaron'))
    assert r and r[1] == ('set_es', 'se inclinaron', 'inclinaron')


def test_reflex_shajah_2sg_te_inclinaras():
    # no te inclinarás (Éx 20:5): IMPF 2ms → clítico «te»
    r = R.check_reflexivo(hw(strongs='H7812', morph='VERBO.HIT.IMPF.P2.M.SG',
                             he='תִשְׁתַּחְוֶה', es='inclinarás'))
    assert r and r[1] == ('set_es', 'te inclinarás', 'inclinarás')


def test_reflex_infinitivo_enclitico():
    r = R.check_reflexivo(hw(strongs='H7812', morph='VERBO.HIT.INFC',
                             he='הִשְׁתַּחֲוֺת', es='inclinar'))
    assert r and r[1] == ('set_es', 'inclinarse', 'inclinar')


def test_reflex_ya_reflexivo_suelto_no_marca():
    assert R.check_reflexivo(hw(strongs='H6915', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                                he='יִּקֹּד', es='se inclinó')) is None


def test_reflex_ya_enclitico_infinitivo_no_marca():
    # postrarnos (infinitivo + enclítico «nos») ya es reflexivo (Gén 37:10)
    assert R.check_reflexivo(hw(strongs='H7812', morph='VERBO.HIT.INFC',
                                he='הִשְׁתַּחֲוֺת', es='postrarnos')) is None


def test_reflex_natah_h5186_transitivo_excluido():
    # נטה H5186 es Hifil TRANSITIVO («inclinar/extender»): NUNCA reflexivo
    assert R.check_reflexivo(hw(strongs='H5186', morph='VERBO.HIF.WAYYIQT.P3.M.SG',
                                he='יַּט', es='inclinó')) is None


def test_reflex_adorar_transitivo_no_marca():
    # שחה glosado «adoró» → adorar es TRANSITIVO en español, sin reflexivo
    assert R.check_reflexivo(hw(strongs='H7812', morph='VERBO.HIT.WAYYIQT.P3.M.SG',
                                he='יִּשְׁתַּחוּ', es='adoró')) is None


def test_reflex_sustantivo_reverencia_no_marca():
    assert R.check_reflexivo(hw(strongs='H7812', morph='VERBO.HIT.WAYYIQT.P3.M.SG',
                                he='יִּשְׁתַּחוּ', es='reverencia')) is None


def test_reflex_participio_no_marca():
    assert R.check_reflexivo(hw(strongs='H7812', morph='VERBO.UNKNOWN: V.PTCA.M.PL',
                                he='מִשְׁתַּחֲוִים', es='inclinado')) is None


def test_reflex_2plural_no_marca():
    # 2ª pl (posible peninsular «inclinaos/inclinéis») → no autofix
    assert R.check_reflexivo(hw(strongs='H7812', morph='VERBO.UNKNOWN: V.SEQ.PERF.P2.M.PL',
                                he='הִשְׁתַּחֲוִיתֶם', es='inclinéis')) is None


def test_reflex_mayuscula_y_conjuncion():
    r = R.check_reflexivo(hw(strongs='H6915', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                             he='יִּקֹּד', es='Inclinó'))
    assert r and r[1] == ('set_es', 'Se inclinó', 'Inclinó')
    r2 = R.check_reflexivo(hw(strongs='H6915', morph='VERBO.QAL.WAYYIQT.P3.M.SG',
                              he='יִּקֹּד', es='y inclinó'))
    assert r2 and r2[1] == ('set_es', 'y se inclinó', 'y inclinó')


def test_reflex_kara_arrodillo_h3766():
    r = R.check_reflexivo(hw(strongs='H3766', morph='VERBO.QAL.WAYYIQT.P3.F.SG',
                             he='תִּכְרַע', es='inclinó'))
    assert r and r[1] == ('set_es', 'se inclinó', 'inclinó')


def test_reflex_shajah_sin_strong_por_esqueleto():
    # sin Strong pero esqueleto Hishtaphel (שתח) → se reconoce
    r = R.check_reflexivo(hw(strongs='', morph='VERBO.HIT.WAYYIQT.P3.M.PL',
                             he='יִשְׁתַּחֲוּוּ', es='inclinen'))
    assert r and r[1][1] == 'se inclinen'


def test_clitico_reflexivo_helper():
    assert R._clitico_reflexivo('VERBO.QAL.WAYYIQT.P1.COMMON.SG') == 'me'
    assert R._clitico_reflexivo('VERBO.QAL.WAYYIQT.P1.COMMON.PL') == 'nos'
    assert R._clitico_reflexivo('VERBO.HIT.IMPF.P2.M.SG') == 'te'
    assert R._clitico_reflexivo('VERBO.QAL.WAYYIQT.P3.M.SG') == 'se'
    assert R._clitico_reflexivo('VERBO.QAL.WAYYIQT.P3.M.PL') == 'se'


# ── BARRERA DE INMUTABILIDAD: el motor solo toca campos del español ──────────
def _doc(hws):
    return {'verses': [{'chapter': 1, 'verse': 1, 'pairs': [{'he_words': hws}]}]}


def test_huella_permite_cambio_es_y_sufijo():
    d = _doc([hw(strongs='H1', morph='SUBS.M.SG.A', he='דָּבָר', es='cosa',
                 prs={'es': 'su', 'he_form': 'וֹ', 'he_morph': 'PRS.P3.M.SG'})])
    antes = R._huella_intocable(d)
    tok = d['verses'][0]['pairs'][0]['he_words'][0]
    tok['es'] = 'palabra'                       # cambio permitido
    tok['prs_suffix']['es'] = 'sus'             # cambio permitido
    tok['prefix_es'] = ['y']                    # cambio permitido
    tok['es_source'] = 'fix'                    # cambio permitido
    assert R._verificar_intocable(antes, R._huella_intocable(d)) == []


def test_huella_detecta_cambio_strongs():
    d = _doc([hw(strongs='H1', morph='SUBS.M.SG.A', he='דָּבָר', es='cosa')])
    antes = R._huella_intocable(d)
    d['verses'][0]['pairs'][0]['he_words'][0]['strongs'] = 'H999'  # INTOCABLE
    assert R._verificar_intocable(antes, R._huella_intocable(d)) == ['1:1']


def test_huella_detecta_cambio_hebreo_y_morfologia():
    d = _doc([hw(strongs='H1', morph='SUBS.M.SG.A', he='דָּבָר', es='cosa')])
    antes = R._huella_intocable(d)
    d['verses'][0]['pairs'][0]['he_words'][0]['he_morph'] = 'VERBO.QAL'  # INTOCABLE
    assert R._verificar_intocable(antes, R._huella_intocable(d)) == ['1:1']


def test_huella_detecta_cambio_sufijo_hebreo():
    d = _doc([hw(strongs='H1', morph='SUBS.M.SG.C', he='אֲחֹת', es='hermana',
                 prs={'es': 'su', 'he_form': 'וֹ', 'he_morph': 'PRS.P3.M.SG'})])
    antes = R._huella_intocable(d)
    d['verses'][0]['pairs'][0]['he_words'][0]['prs_suffix']['he_form'] = 'X'  # INTOCABLE
    assert R._verificar_intocable(antes, R._huella_intocable(d)) == ['1:1']


def test_huella_detecta_reordenamiento():
    d = _doc([hw(strongs='H1', he='א', es='a'), hw(strongs='H2', he='ב', es='b')])
    antes = R._huella_intocable(d)
    ws = d['verses'][0]['pairs'][0]['he_words']
    ws[0], ws[1] = ws[1], ws[0]                 # reordenar = violación
    assert R._verificar_intocable(antes, R._huella_intocable(d)) == ['1:1']


def test_concord_articulo_genero_es_autofix():
    # «el tienda»→«la tienda»: género femenino SEGURO (-a) → ahora AUTOFIX,
    # no reporte. Error gramatical objetivo de la misma palabra.
    tok = hw(strongs='H168', morph='SUBS.F.SG.A', he='אֹהֶל', es='tienda',
             prefix_es=['el'])
    out = R.check_concord(tok)
    assert out and out[0][1] == ('pfx_set', 0, 'la', 'el')
    d = _doc([tok])
    fnd = R.F('CONCORD', 1, 1, 0, 0, 'אֹהֶל', 'SUBS.F.SG.A', 'x',
              suggest=('pfx_set', 0, 'la', 'el'))
    n = R.apply_safe(d, [fnd], slug=None)
    assert n == 1
    assert d['verses'][0]['pairs'][0]['he_words'][0]['prefix_es'][0] == 'la'


def test_concord_articulo_genero_ambiguo_no_autofix():
    # sustantivo de género DESCONOCIDO (termina en consonante, no en listas):
    # expected_article devuelve None → no se marca por género (solo por número)
    assert R.expected_article('rey') is None
    out = R.check_concord(hw(strongs='H4428', morph='SUBS.M.SG.A', he='מֶלֶךְ',
                             es='rey', prefix_es=['la']))
    # 'la rey': número concuerda (sg), género desconocido → NO se marca
    assert out == []


def test_concord_excepcion_maná_no_falso_positivo():
    # «el maná» es correcto (maná es masculino pese a -á): NO debe marcarse
    assert R.expected_article('maná') == 'el'
    assert R.check_concord(hw(morph='SUBS.M.SG.A', he='מָן', es='maná',
                              prefix_es=['el'])) == []


def test_concord_adverbio_invariable_no_falso_positivo():
    # «afuera» (חוצה, adverbio con he direccional, morf SUBS) termina en -a pero
    # NO es sustantivo femenino: expected_article NO opina → sin autofix «la afuera»
    assert R.expected_article('afuera') is None
    assert R.check_concord(hw(morph='SUBS.M.SG.A', he='ח֖וּצָה', es='afuera',
                              prefix_es=['el'])) == []


def test_translit_mayuscula_nombre_propio_autofix():
    # gentilicio en minúscula «cananeos»→«Cananeos»: AUTOFIX (solo casing)
    tok = hw(strongs='H3669', morph='GENT.M.PL.A', he='כְּנַעֲנִי', es='cananeos')
    r = R.check_translit(tok)
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Cananeos', 'cananeos')
    d = _doc([tok])
    fnd = R.F('TRANSLIT', 1, 1, 0, 0, 'כְּנַעֲנִי', 'GENT.M.PL.A', r[0],
              suggest=r[1])
    n = R.apply_safe(d, [fnd], slug=None)
    assert n == 1
    assert d['verses'][0]['pairs'][0]['he_words'][0]['es'] == 'Cananeos'


def test_translit_apostrofo_no_se_toca():
    # «'Elohim» empieza por apóstrofo (no alfabético) → NO se marca minúscula
    assert R.check_translit(hw(morph='NPROP.M.SG.A', he='X', es="'Elohim")) is None


def test_translit_compuesto_queda_reporte():
    # topónimo compuesto en minúscula → REPORTE (string), no autofix a medias
    r = R.check_translit(hw(morph='NPROP.M.SG.A', he='X', es='mar rojo'))
    assert isinstance(r, str)


def test_translit_lexema_goy_plural_naciones():
    # גוים H1471 SUBS.M.PL.A glosado «naciones» → «Goyim» (lexema lista maestra)
    tok = hw(strongs='H1471', morph='SUBS.M.PL.A', he='גּוֹיִם', es='naciones')
    r = R.check_translit_lexema(tok)
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Goyim', 'naciones')
    d = _doc([tok])
    fnd = R.F('TRANSLIT', 1, 1, 0, 0, 'גּוֹיִם', 'SUBS.M.PL.A', r[0], suggest=r[1])
    assert R.apply_safe(d, [fnd], slug=None) == 1
    assert d['verses'][0]['pairs'][0]['he_words'][0]['es'] == 'Goyim'


def test_translit_lexema_goy_singular_nacion():
    # גוי H1471 SUBS.M.SG.A glosado «nación» → «Goy»
    r = R.check_translit_lexema(hw(strongs='H1471', morph='SUBS.M.SG.A',
                                   he='גּוֹי', es='nación'))
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Goy', 'nación')


def test_translit_lexema_goy_constructo_no_autofix():
    # constructo .C (grafía «Goyei») → NO autofix (queda a mano/reporte)
    assert R.check_translit_lexema(hw(strongs='H1471', morph='SUBS.M.PL.C',
                                      he='גּוֹיֵי', es='naciones de')) is None


def test_translit_lexema_goy_ya_transliterado_no_toca():
    # ya está «Goyim» → no re-marca
    assert R.check_translit_lexema(hw(strongs='H1471', morph='SUBS.M.PL.A',
                                      he='גּוֹיִם', es='Goyim')) is None


def test_translit_lexema_goy_glosa_no_autorizada_no_toca():
    # glosa rara fuera del set autorizado → no arriesga
    assert R.check_translit_lexema(hw(strongs='H1471', morph='SUBS.M.PL.A',
                                      he='גּוֹיִם', es='multitud')) is None


def test_translit_lexema_otro_strong_no_toca():
    # otro Strong no listado → no actúa
    assert R.check_translit_lexema(hw(strongs='H5971', morph='SUBS.M.SG.A',
                                      he='עַם', es='pueblo')) is None


def test_translit_shivah_seba():
    r = R.check_translit_lexema(hw(strongs='H7656', morph='ADJ.M.SG.A',
                                   he='שִׁבְעָה', es='seba'))
    assert isinstance(r, tuple) and r[1] == ('set_es', "Shiv'áh", 'seba')


def test_translit_beruj_participio_amparado_de():
    r = R.check_translit_lexema(hw(strongs='H1288', morph='VERBO.QAL.PTCP.M.SG',
                                   he='בְּרוּךְ', es='amparado de'))
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Beruj de', 'amparado de')
    # el verbo finito «amparó» NO se translitera
    assert R.check_translit_lexema(hw(strongs='H1288', morph='VERBO.QAL.QATAL.P3.M.SG',
                                      he='וַיְבָרֶךְ', es='amparó')) is None


def test_translit_berajah_amparo():
    r = R.check_translit_lexema(hw(strongs='H1293', morph='SUBS.F.SG.A',
                                   he='בְרָכָה', es='amparo'))
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Berajáh', 'amparo')
    r2 = R.check_translit_lexema(hw(strongs='H1293', morph='SUBS.F.SG.A',
                                    he='בְרָכָה', es='bendición'))
    assert isinstance(r2, tuple) and r2[1] == ('set_es', 'Berajáh', 'bendición')
    # constructo Birkat: no autofix (grafía distinta)
    assert R.check_translit_lexema(hw(strongs='H1293', morph='SUBS.F.SG.C',
                                      he='בִּרְכַּת', es='bendición de')) is None


def test_translit_qelalah_desamparo():
    r = R.check_translit_lexema(hw(strongs='H7045', morph='SUBS.F.SG.A',
                                   he='קְלָלָה', es='desamparo'))
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Qelaláh', 'desamparo')
    r2 = R.check_translit_lexema(hw(strongs='H7045', morph='SUBS.F.SG.A',
                                    he='קְלָלָה', es='maldición'))
    assert isinstance(r2, tuple) and r2[1] == ('set_es', 'Qelaláh', 'maldición')


def test_translit_beerseba_segundo_eslabon():
    r = R.check_translit_lexema(hw(strongs='H7651,H875', morph='ADJ.F.SG.A',
                                   he='שֶׁבַע', es='beerseba'))
    assert isinstance(r, tuple) and r[1] == ('set_es', 'Shéva', 'beerseba')


# ── H430 אֱלֹהִים → 'Elohim (apelativo divino, forma exacta) ───────────────────
def test_translit_lexema_h430_dios_a_elohim():
    # H430 absoluto glosado «dios» (Dios verdadero) → 'Elohim (los 59 hermanos ya)
    tok = hw(strongs='H430', morph='SUBS.M.PL.A', he='אֱלֹהִים', es='dios')
    r = R.check_translit_lexema(tok)
    assert isinstance(r, tuple) and r[1] == ('set_es', "'Elohim", 'dios')
    d = _doc([tok])
    fnd = R.F('TRANSLIT', 1, 1, 0, 0, 'אֱלֹהִים', 'SUBS.M.PL.A', r[0], suggest=r[1])
    assert R.apply_safe(d, [fnd], slug=None) == 1
    assert d['verses'][0]['pairs'][0]['he_words'][0]['es'] == "'Elohim"


def test_translit_lexema_h430_ya_elohim_no_toca():
    # ya está «'Elohim» → no re-marca (apóstrofo del álef indiferente)
    assert R.check_translit_lexema(hw(strongs='H430', morph='SUBS.M.PL.A',
                                      he='אֱלֹהִים', es="'Elohim")) is None


def test_translit_lexema_h430_dioses_paganos_no_toca():
    # plural pagano «dioses» (dioses ajenos) NO está en trad → se respeta minúscula
    assert R.check_translit_lexema(hw(strongs='H430', morph='SUBS.M.PL.A',
                                      he='אֱלֹהִים', es='dioses')) is None


def test_translit_lexema_h430_constructo_no_autofix():
    # constructo «dios de» (grafía 'Elohei) → NO autofix; lo lista MORPH_MISMATCH
    assert R.check_translit_lexema(hw(strongs='H430', morph='SUBS.M.PL.C',
                                      he='אֱלֹהֵי', es='dios de')) is None


def test_translit_lexema_h430_ciertamente_no_toca():
    # glosa mal etiquetada «ciertamente» fuera del set → no arriesga
    assert R.check_translit_lexema(hw(strongs='H430', morph='SUBS.M.PL.A',
                                      he='אֱלֹהִים', es='ciertamente')) is None


def test_morph_mismatch_h430_absoluto_defiere_a_translit():
    # el absoluto «dios» lo autofixea TRANSLIT → MORPH_MISMATCH NO lo reporta
    assert R.check_morph_mismatch(hw(strongs='H430', morph='SUBS.M.PL.A',
                                     he='אֱלֹהִים', es='dios')) is None


def test_morph_mismatch_h430_constructo_si_reporta():
    # el constructo «dios de» (no autofixable) SÍ se lista para mano
    r = R.check_morph_mismatch(hw(strongs='H430', morph='SUBS.M.PL.C',
                                  he='אֱלֹהֵי', es='dios de'))
    assert r and 'nombre divino' in r


# ── PRON.PERS: género/número por morfología (הִוא pentateucal = femenino) ──────
def test_pron_pers_hiw_pentateucal_femenino_a_ella():
    # הִוא (con vav) P3.F.SG glosado «él» → «ella» (Gén 26:7)
    out = R.check_pron(hw(strongs='H1931', morph='PRON.PERS.P3.F.SG',
                          he='הִוא', es='él'))
    assert out and out[0][1] == ('set_es', 'ella', 'él')


def test_pron_pers_masc_glosado_ella_a_el():
    # P3.M.SG glosado «ella» → «él»
    out = R.check_pron(hw(strongs='H1931', morph='PRON.PERS.P3.M.SG',
                          he='הוּא', es='ella'))
    assert out and out[0][1] == ('set_es', 'él', 'ella')


def test_pron_pers_plural_femenino_a_ellas():
    # P3.F.PL glosado «ellos» → «ellas»
    out = R.check_pron(hw(strongs='H2007', morph='PRON.PERS.P3.F.PL',
                          he='הֵנָּה', es='ellos'))
    assert out and out[0][1] == ('set_es', 'ellas', 'ellos')


def test_pron_pers_correcto_no_toca():
    # ya concuerda (P3.F.SG = «ella») → no marca
    assert R.check_pron(hw(strongs='H1931', morph='PRON.PERS.P3.F.SG',
                           he='הִיא', es='ella')) == []


def test_pron_pers_conserva_mayuscula():
    # respeta la mayúscula inicial (inicio de oración)
    out = R.check_pron(hw(strongs='H1931', morph='PRON.PERS.P3.F.SG',
                          he='הִוא', es='Él'))
    assert out and out[0][1] == ('set_es', 'Ella', 'Él')


def test_pron_pers_1a_2a_persona_no_toca():
    # solo 3ª persona: no arriesga «tú/yo/nosotros» (convención editorial)
    assert R.check_pron(hw(strongs='H859', morph='PRON.PERS.P2.M.SG',
                           he='אַתָּה', es='él')) == []


def test_pron_pers_glosa_contextual_no_toca():
    # glosa de más de una palabra (contextual) → no la toca
    assert R.check_pron(hw(strongs='H1931', morph='PRON.PERS.P3.F.SG',
                           he='הִוא', es='él mismo')) == []


def test_poses_pronombre_sujeto_en_raiz_autofix():
    # «él pies» + suf «su» (dual) → «sus pies» + limpiar sufijo (Gén 24:32)
    tok = hw(strongs='H7272', morph='SUBS.F.DU.C', he='רַגְלָיו', es='él pies',
             prs={'he_morph': 'PRS.P3.M.SG', 'es': 'su'})
    r = R.check_poses(tok)
    assert r and r[1] == ('poss_rehome', 'él pies', 'sus pies', 'su')
    d = _doc([tok])
    fnd = R.F('POSES', 1, 1, 0, 0, 'רַגְלָיו', 'SUBS.F.DU.C', r[0], suggest=r[1])
    n = R.apply_safe(d, [fnd], slug=None)
    assert n == 1
    t = d['verses'][0]['pairs'][0]['he_words'][0]
    assert t['es'] == 'sus pies' and t['prs_suffix']['es'] == ''


def test_poses_pronombre_sujeto_singular_da_su():
    # «ella boca» + suf «su» (F.SG) → «su boca» (sustantivo singular)
    tok = hw(strongs='H6310', morph='SUBS.M.SG.C', he='פִּיהָ', es='ella boca',
             prs={'he_morph': 'PRS.P3.F.SG', 'es': 'su'})
    r = R.check_poses(tok)
    assert r and r[1] == ('poss_rehome', 'ella boca', 'su boca', 'su')


def test_poses_pronombre_sujeto_con_verbo_es_reporte():
    # «ella fueron» (raíz corrupta con verbo) → NO autofix, solo reporte
    tok = hw(strongs='H1121', morph='SUBS.M.PL.C', he='בָנֶיהָ', es='ella fueron',
             prs={'he_morph': 'PRS.P3.F.SG', 'es': 'su'})
    r = R.check_poses(tok)
    assert r and r[1] is None


def test_poses_pronombre_sujeto_con_cuantificador_es_reporte():
    # «ellos todos» → «todos» no es sustantivo → reporte (no «sus todos»)
    tok = hw(strongs='H3605', morph='SUBS.M.SG.C', he='כֻּלָּם', es='ellos todos',
             prs={'he_morph': 'PRS.P3.M.PL', 'es': 'su'})
    r = R.check_poses(tok)
    assert r and r[1] is None


def test_apply_safe_homograf_no_toca_intocables():
    # HOMOGRAF real (עם «pueblo»→con) NO debe alterar hebreo/strongs/morfología
    tok = hw(strongs='H5973', morph='PREP', he='עִם', es='pueblo')
    d = _doc([tok])
    antes = R._huella_intocable(d)
    fnd = R.F('HOMOGRAF', 1, 1, 0, 0, 'עִם', 'PREP',
              'x', suggest=('set_es', 'con', 'pueblo'))
    R.apply_safe(d, [fnd], slug=None)
    assert d['verses'][0]['pairs'][0]['he_words'][0]['es'] == 'con'  # sí cambió es
    assert R._verificar_intocable(antes, R._huella_intocable(d)) == []  # nada más


def test_refuerzo_verde_manda_y_autofix():
    import estilo_usuario as EU
    prev = EU._refuerzo
    EU._refuerzo = [{
        'strongs': 'H5046',
        'morph': 'VERBO.HIF.WAYYIQT.P3.M.PL',
        'esqueleto': 'יגדו',
        'es_antes': 'nuevas',
        'es_despues': 'dijeron',
    }]
    try:
        pref = EU.preferida('H5046', 'VERBO.HIF.WAYYIQT.P3.M.PL')
        assert pref and pref[0] == 'dijeron'
        pick = EU.sugerir('H5046', 'VERBO.HIF.WAYYIQT.P3.M.PL', 'nuevas')
        assert pick and pick['sugerida'] == 'dijeron' and pick.get('via') == 'verde'
        assert EU.sugerir('H5046', 'VERBO.HIF.WAYYIQT.P3.M.PL', 'dijeron') is None
        assert EU.glosa_conocida('H5046', 'VERBO.HIF.WAYYIQT.P3.M.PL', 'dijeron')
        tok = hw(strongs='H5046', morph='VERBO.HIF.WAYYIQT.P3.M.PL',
                 he='יגדו', es='nuevas')
        d = {'verses': [verse(1, 1, tok)]}
        findings, _, _, _ = R.run(
            d, '__test__', ((1, 1), (1, 999)), ((1, 1), (1, 999)), 2, {'REFUERZO'})
        assert any(f.cat == 'REFUERZO' for f in findings)
        n = R.apply_safe(d, findings, slug=None)
        assert n == 1 and d['verses'][0]['pairs'][0]['he_words'][0]['es'] == 'dijeron'
    finally:
        EU._refuerzo = prev


# ── Parentesco tónico (hijo mío) + ברך verbo translit ───────────────────────
def test_parentesco_mi_hijo_a_hijo_mio():
    # «mi hijo» + sufijo P1 → «hijo mío» fusionado (limpia sufijo)
    tok = hw(strongs='', morph='SUBS.M.SG.C', he='בְּנִ', es='mi hijo',
             prs={'he_morph': 'PRS.P1.COMMON.SG', 'he_form': 'י', 'es': 'mi'})
    r = R.check_poses(tok)
    assert r and r[1] == ('idiom', 'hijo mío', 'mi hijo')


def test_parentesco_hijo_mio_tilde():
    # «hijo mio» (sin tilde) → «hijo mío»
    tok = hw(strongs='', morph='SUBS.M.SG.C', he='בְּנִ', es='hijo mio',
             prs={'he_morph': 'PRS.P1.COMMON.SG', 'he_form': 'י', 'es': ''})
    r = R.check_poses(tok)
    assert r and r[1] == ('set_es', 'hijo mío', 'hijo mio')


def test_parentesco_hijo_mas_sufijo_mi():
    # «hijo»+mi → «hijo mío»
    tok = hw(strongs='H1121', morph='SUBS.M.SG.C', he='בְּנִ', es='hijo',
             prs={'he_morph': 'PRS.P1.COMMON.SG', 'he_form': 'י', 'es': 'mi'})
    r = R.check_poses(tok)
    assert r and r[1] == ('idiom', 'hijo mío', 'hijo')


def test_parentesco_su_hijo_no_toca():
    # 3ª persona: no es vocativo «mío»
    tok = hw(strongs='H1121', morph='SUBS.M.SG.C', he='בְּנֹו', es='su hijo',
             prs={'he_morph': 'PRS.P3.M.SG', 'he_form': 'וֹ', 'es': ''})
    assert R.check_parentesco_tonico(tok) is None


def test_translit_barak_tevarejja():
    # תְּבָרֶכְךָ «te bendiga» → Tevarejjá (motor fonético)
    tok = hw(strongs='', morph='VERBO.PIEL.IMPF.P3.F.SG', he='תְּבָרֶכְ',
             es='bendiga',
             prs={'he_morph': 'PRS.P2.M.SG', 'he_form': 'ךָ', 'es': 'te'})
    r = R.check_translit_barak_verb(tok)
    assert r and r[1][0] == 'idiom' and r[1][1] == 'Tevarejjá'


def test_translit_barak_no_toca_sustantivo():
    # H1293 Berajáh (sustantivo) no entra por el check de verbo
    tok = hw(strongs='H1293', morph='SUBS.F.SG.A', he='בְרָכָה', es='amparo')
    assert R.check_translit_barak_verb(tok) is None


def test_translit_beraja_qelala_suf():
    # קִלְלָתְךָ «tu maldición» → Qillatjá vía fonética
    tok = hw(strongs='', morph='SUBS.F.SG.C', he='קִלְלָתְ', es='tu maldición',
             prs={'he_morph': 'PRS.P2.M.SG', 'he_form': 'ךָ', 'es': ''})
    r = R.check_translit_beraja_qelala_suf(tok)
    assert r and r[1][0] in ('set_es', 'idiom') and r[1][1] == 'Qillatjá'


# ── runner propio (sin pytest) ───────────────────────────────────────────────
def _run_all():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith('test_') and callable(o)]
    ok = fail = 0
    for name, fn in tests:
        try:
            fn()
            print(f'  PASS  {name}')
            ok += 1
        except AssertionError as e:
            print(f'  FAIL  {name}: {e}')
            fail += 1
        except Exception as e:
            print(f'  ERROR {name}: {type(e).__name__}: {e}')
            fail += 1
    print(f'\n{ok} PASS · {fail} FAIL · {len(tests)} total')
    return 1 if fail else 0


if __name__ == '__main__':
    raise SystemExit(_run_all())
