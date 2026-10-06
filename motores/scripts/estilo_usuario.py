# -*- coding: utf-8 -*-
"""
Lector del modelo estadístico de redacción del usuario (estadistica_glosas.json).

Provee la palabra que el usuario usa con MAYOR frecuencia para una palabra
hebrea (por Strong + morfología), para que el motor sugiera/escoja según
"tu forma de escribir". Report-only: sugiere, no impone.
"""
import json
import re
import unicodedata
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / 'fuentes' / 'estadistica_glosas.json'
_REFUERZO_PATH = Path(__file__).resolve().parents[2] / 'fuentes' / 'refuerzo_estilo.json'
_cache = None
_sk_cache = None
_refuerzo = None  # None = no cargado; list = entradas (la última gana)
_NIQ = re.compile(r'[\u0591-\u05C7]')


def consk(s):
    s = _NIQ.sub('', s or '')
    return ''.join(c for c in s if 0x05D0 <= ord(c) <= 0x05EA)

# Umbrales de confianza para SUGERIR un cambio de estilo.
MIN_N = 5        # muestras mínimas de la forma
MIN_PCT = 70.0   # % mínimo de la preferida
MAX_CUR_PCT = 25.0  # si la glosa actual ya representa >25% de tu uso, NO se toca


def _load():
    global _cache, _sk_cache
    if _cache is None:
        try:
            payload = json.loads(_PATH.read_text(encoding='utf-8'))
            _cache = payload.get('lexemas', {})
            _sk_cache = payload.get('por_esqueleto', {})
        except Exception:
            _cache, _sk_cache = {}, {}
    return _cache


def _load_sk():
    if _sk_cache is None:
        _load()
    return _sk_cache or {}


def _load_refuerzo():
    """Correcciones verdes: tu español (es_despues). El hebreo solo identifica."""
    global _refuerzo
    if _refuerzo is None:
        try:
            payload = json.loads(_REFUERZO_PATH.read_text(encoding='utf-8'))
            arr = payload.get('entradas') if isinstance(payload, dict) else payload
            _refuerzo = arr if isinstance(arr, list) else []
        except Exception:
            _refuerzo = []
    return _refuerzo


def _refuerzo_glosa(strongs, morph=None, sk=None):
    """Última glosa ES marcada en verde para esa forma. None si no hay."""
    st = _norm_strong(strongs) if strongs else ''
    morph = (morph or '').strip()
    sk = sk or ''
    hit = None
    for e in _load_refuerzo():
        if not isinstance(e, dict):
            continue
        despues = _norm(e.get('es_despues') or '')
        if not despues:
            continue
        est = _norm_strong(e.get('strongs') or '')
        em = (e.get('morph') or '').strip()
        esk = (e.get('esqueleto') or '').strip()
        if st and est == st and (not morph or not em or em == morph):
            hit = despues
        elif (not st or not est) and sk and esk == sk and (not morph or not em or em == morph):
            hit = despues
    return hit


def _norm_strong(st):
    st = (st or '').strip().upper()
    m = re.match(r'^([HG])0*(\d+)$', st)
    return f'{m.group(1)}{m.group(2)}' if m else st


def _norm(s):
    return unicodedata.normalize('NFC', (s or '').strip())


def preferida(strongs, morph=None):
    """Devuelve (glosa, pct, n, ambigua) preferida para (Strong, morf).
    Si morf no está o no alcanza min_n, cae al nivel de lema. None si nada.
    Una corrección VERDE tuya manda sobre la estadística."""
    verde = _refuerzo_glosa(strongs, morph)
    if verde:
        return (verde, 100.0, 1, False)
    e = _load().get(_norm_strong(strongs))
    if not e:
        return None
    if morph:
        fe = e.get('formas', {}).get(morph)
        if fe and fe['total'] >= 1:
            return (fe['preferida'], fe['pct'], fe['total'], fe['ambigua'])
    if e.get('lema_preferida'):
        return (e['lema_preferida'], e.get('lema_pct'), e.get('total'), e.get('lema_ambiguo'))
    return None


def preferida_sk(sk, morph=None):
    """Como preferida() pero POR ESQUELETO (respaldo sin Strong).
    Devuelve (glosa, pct, n, ambigua) o None."""
    verde = _refuerzo_glosa('', morph, sk=sk)
    if verde:
        return (verde, 100.0, 1, False)
    fe = _load_sk().get(sk, {}).get(morph) if morph else None
    if fe and fe['total'] >= 1:
        return (fe['preferida'], fe['pct'], fe['total'], fe['ambigua'])
    return None


def sugerir(strongs, morph, current_es):
    """Sugiere tu glosa mayoritaria si la actual se desvía claramente.

    Devuelve dict {sugerida, pct, n, actual_pct} o None. Alta señal:
    forma con n>=MIN_N, no ambigua, preferida>=MIN_PCT y la glosa actual
    representa <=MAX_CUR_PCT de tu uso (o no aparece).
    Corrección VERDE: sugiere tu español aunque n=1."""
    verde = _refuerzo_glosa(strongs, morph)
    if verde:
        cur = _norm(current_es)
        if cur and cur != _norm(verde):
            return {'sugerida': verde, 'pct': 100.0, 'n': 1,
                    'actual_pct': 0.0, 'via': 'verde'}
        return None
    e = _load().get(_norm_strong(strongs))
    if not e or not morph:
        return None
    fe = e.get('formas', {}).get(morph)
    if not fe or fe['total'] < MIN_N or fe['ambigua']:
        return None
    pref = _norm(fe['preferida'])
    cur = _norm(current_es)
    if not cur or cur == pref:
        return None
    if fe['pct'] < MIN_PCT:
        return None
    cur_pct = next((g['pct'] for g in fe['glosas'] if _norm(g['es']) == cur), 0.0)
    if cur_pct > MAX_CUR_PCT:
        return None
    return {'sugerida': fe['preferida'], 'pct': fe['pct'],
            'n': fe['total'], 'actual_pct': cur_pct}


def sugerir_ctx(strongs, morph, current_es, prev_ck='', next_ck=''):
    """Sugerencia SENSIBLE AL CONTEXTO para formas AMBIGUAS.

    Cuando una (Strong, morf) es ambigua (usas varios términos según el caso),
    `sugerir()` se abstiene. Aquí se mira el vecino (esqueleto consonántico
    anterior/siguiente): si en ESE contexto tu uso tiene un ganador claro y la
    glosa actual no coincide, se sugiere el término que sueles poner en ese
    contexto. Prioriza el vecino SIGUIENTE (colocación N1+N2), luego el anterior.

    Devuelve {sugerida, pct, n, ctx, actual_pct} o None. Report-only."""
    e = _load().get(_norm_strong(strongs))
    if not e or not morph:
        return None
    fe = e.get('formas', {}).get(morph)
    if not fe or not fe.get('ambigua'):
        return None
    ctx = fe.get('ctx') or {}
    cur = _norm(current_es)
    for side, ck in (('next', _norm(next_ck)), ('prev', _norm(prev_ck))):
        w = (ctx.get(side) or {}).get(ck)
        if not w:
            continue
        pref = _norm(w['es'])
        if not cur or cur == pref:
            return None            # ya coincide con tu uso en este contexto → ok
        return {'sugerida': w['es'], 'pct': w['pct'], 'n': w['n'],
                'ctx': f'{side} «{ck}»', 'actual_pct': None}
    return None


def sugerir_sk(sk, morph, current_es):
    """Como sugerir() pero POR ESQUELETO consonántico. Respaldo para tokens
    SIN Strong (o cuyo Strong no tiene datos): p.ej. מלאך→'mensajero'."""
    verde = _refuerzo_glosa('', morph, sk=sk)
    if verde:
        cur = _norm(current_es)
        if cur and cur != _norm(verde):
            return {'sugerida': verde, 'pct': 100.0, 'n': 1,
                    'actual_pct': 0.0, 'via': 'verde'}
        return None
    fe = _load_sk().get(sk, {}).get(morph)
    if not fe or fe['total'] < MIN_N or fe['ambigua']:
        return None
    pref = _norm(fe['preferida'])
    cur = _norm(current_es)
    if not cur or cur == pref or fe['pct'] < MIN_PCT:
        return None
    cur_pct = next((g['pct'] for g in fe['glosas'] if _norm(g['es']) == cur), 0.0)
    if cur_pct > MAX_CUR_PCT:
        return None
    return {'sugerida': fe['preferida'], 'pct': fe['pct'], 'n': fe['total'],
            'actual_pct': cur_pct, 'via': 'esqueleto'}


def sugerir_ctx_sk(sk, morph, current_es, prev_ck='', next_ck=''):
    """Como sugerir_ctx() pero por esqueleto (formas ambiguas sin Strong)."""
    fe = _load_sk().get(sk, {}).get(morph)
    if not fe or not fe.get('ambigua'):
        return None
    ctx = fe.get('ctx') or {}
    cur = _norm(current_es)
    for side, ck in (('next', _norm(next_ck)), ('prev', _norm(prev_ck))):
        w = (ctx.get(side) or {}).get(ck)
        if not w:
            continue
        pref = _norm(w['es'])
        if not cur or cur == pref:
            return None
        return {'sugerida': w['es'], 'pct': w['pct'], 'n': w['n'],
                'ctx': f'{side} «{ck}» (esqueleto)', 'actual_pct': None,
                'via': 'esqueleto'}
    return None


def _glosa_en(fe, cur):
    return any(_norm(g['es']).lower() == cur for g in (fe.get('glosas') or []))


def glosa_conocida(strongs, morph, current_es):
    """True si `current_es` figura entre TUS glosas observadas para ese lexema
    (por forma o a nivel de lema). Sirve para NO tratar como corrupción una glosa
    que en realidad usas (p.ej. el numeral «un» de H259, o una preposición-
    sustantivo legítima). False si el Strong no está en la estadística (sin
    evidencia → el llamador decide con otra señal)."""
    cur = _norm(current_es).lower()
    verde = _refuerzo_glosa(strongs, morph)
    if verde and _norm(verde).lower() == cur:
        return True
    e = _load().get(_norm_strong(strongs))
    if not e:
        return False
    fe = e.get('formas', {}).get(morph) if morph else None
    if fe and _glosa_en(fe, cur):
        return True
    return any(_norm(g['es']).lower() == cur for g in (e.get('lema_glosas') or []))


def glosa_conocida_sk(sk, morph, current_es):
    """Como glosa_conocida() pero POR ESQUELETO (respaldo sin Strong)."""
    cur = _norm(current_es).lower()
    verde = _refuerzo_glosa('', morph, sk=sk)
    if verde and _norm(verde).lower() == cur:
        return True
    fe = _load_sk().get(sk, {}).get(morph) if morph else None
    return bool(fe and _glosa_en(fe, cur))


def disponible():
    return bool(_load())
