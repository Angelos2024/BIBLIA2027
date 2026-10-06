# -*- coding: utf-8 -*-
"""
Motor de RESTAURACIÓN HEBREA desde OSHB (piloto: Génesis).

Problema: el hebreo del sitio se derivó de CATSS (dobletes, transposiciones,
aparato) y no coincide con el MT limpio (OSHB): hay tokens duplicados/espurios.

Estrategia (reconstrucción): por verso, se RECONSTRUYE la capa hebrea (he_words)
a partir de los tokens de OSHB, garantizando que el texto consonántico = OSHB.
El español y el griego existentes se RE-MAPEAN a la palabra correcta por
alineación LCS (candado). El griego de cada par (gr_unicode) NUNCA se toca y el
conjunto de pares se preserva (no se añaden/eliminan/relabelan pares).

Candado / garantías:
  - gr_unicode de cada par queda byte-idéntico.
  - Mismo número y orden de pares.
  - Texto consonántico del verso == OSHB (si no se logra → se OMITE el verso).
  - Huecos de OSHB (palabra que el sitio sí trae y OSHB no, p.ej. בו en 1:11):
    el verso se OMITE (se deja intacto) y se reporta, para no perder hebreo válido.

Por defecto es DRY-RUN. Con --apply escribe (hace su propio respaldo).
"""
import argparse
import copy
import datetime
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paso5_utils import (set_active_book, load_active, fold_he, parse_ref,
                         verse_ref, iter_oshb_tokens, list_site_tokens,
                         oshb_concatenated, site_concatenated, OshbToken)
from book_config import resolve, ANGELOS
from _rebuild_oshb_from_macula import to_dotted

sys.stdout.reconfigure(encoding="utf-8")

# ── Fuente de verdad hebrea: 'oshb' (oshb-morph) o 'macula' (MT completo) ──
MACULA_TSV = ANGELOS / "IdiomaORIGEN" / "macula-hebrew.tsv"
# slug del proyecto -> código de libro en macula-hebrew.tsv (39 libros del AT)
SLUG_TO_MACULA = {
    "genesis": "GEN", "exodo": "EXO", "levitico": "LEV", "numeros": "NUM",
    "deuteronomio": "DEU", "josue": "JOS", "jueces": "JDG", "rut": "RUT",
    "1_samuel": "1SA", "2_samuel": "2SA", "1_reyes": "1KI", "2_reyes": "2KI",
    "1_cronicas": "1CH", "2_cronicas": "2CH", "esdras": "EZR", "nehemias": "NEH",
    "ester": "EST", "job": "JOB", "salmos": "PSA", "proverbios": "PRO",
    "eclesiastes": "ECC", "cantares": "SNG", "isaias": "ISA", "jeremias": "JER",
    "lamentaciones": "LAM", "ezequiel": "EZK", "daniel": "DAN", "oseas": "HOS",
    "joel": "JOL", "amos": "AMO", "abdias": "OBA", "jonas": "JON",
    "miqueas": "MIC", "nahum": "NAM", "habacuc": "HAB", "sofonias": "ZEP",
    "hageo": "HAG", "zacarias": "ZEC", "malaquias": "MAL",
}
_MACULA_CACHE = {}


def load_macula(slug):
    """(ch,vs) -> lista de (form, morph_dotted) desde macula-hebrew.tsv."""
    if slug in _MACULA_CACHE:
        return _MACULA_CACHE[slug]
    import csv
    code = SLUG_TO_MACULA.get(slug)
    out = {}
    with open(MACULA_TSV, encoding="utf-8") as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            ref = row.get("ref", "")
            if not ref.startswith(code + " "):
                continue
            cv = ref.split(" ", 1)[1].split("!")[0]
            try:
                ch, vs = cv.split(":"); ch = int(ch); vs = int(vs)
            except ValueError:
                continue
            morph = to_dotted(row.get("pos", ""), row.get("stem", ""),
                              row.get("type", ""), row.get("person", ""),
                              row.get("gender", ""), row.get("number", ""),
                              row.get("state", ""))
            out.setdefault((ch, vs), []).append((row.get("text", ""), morph))
    _MACULA_CACHE[slug] = out
    return out


def macula_tokens(slug, ch, vs):
    toks = []
    for i, (form, morph) in enumerate(load_macula(slug).get((ch, vs), [])):
        if not fold_he(form) and form.strip() in ("\u05be", "-", ""):
            continue
        toks.append(OshbToken(ref=f"{ch}:{vs}", idx=i, fold=fold_he(form),
                              form=form, morph=morph or ""))
    return toks


def src_tokens(source, slug, ch, vs):
    return macula_tokens(slug, ch, vs) if source == "macula" else iter_oshb_tokens(ch, vs)


def src_concat_fold(source, slug, ch, vs):
    if source == "macula":
        return fold_he("".join(f for f, _ in load_macula(slug).get((ch, vs), [])))
    return fold_he(oshb_concatenated(ch, vs, False))

PREFIX_HEADS = ("CONJ", "PREP", "ART", "PRT", "INTERR", "INTJ")

# Glosas "función" cuya pérdida (al quitar un duplicado) es inocua.
FUNC_GLOSS = {
    "a", "en", "de", "la", "el", "los", "las", "un", "una", "y", "o", "su", "sus",
    "mi", "mis", "para", "por", "con", "sin", "al", "del", "lo", "le", "les", "se",
    "que", "es", "como", "a ti", "a él", "a ella", "para él", "para ella",
    "para nosotros", "en él", "en ella", "sobre", "cual", "tu", "tus", "nos", "me",
    "te", "vuestro", "vuestra", "todo", "toda", "esto", "esta", "ese", "esa",
    "mí", "ti", "ha",
}


def is_func_gloss(g: str) -> bool:
    g2 = (g or "").strip().lower()
    if not g2:
        return True
    if g2 in FUNC_GLOSS:
        return True
    # placeholders no-curados en inglés: compuestos con punto ('of.tent',
    # 'it.was.put', 'they.sent.away', 'do.evil') o marcador '[EN:...]'.
    # NO se marca cualquier ascii suelto: palabras españolas sin acento
    # ('caminaron', 'pusieron', 'reverencia') son contenido real.
    if g2.startswith("[en:"):
        return True
    if "." in g2 and all(c.isascii() for c in g2):
        return True
    return False


def role_of(morph: str) -> str:
    head = (morph or "").split(".")[0].split("+")[0]
    if head in PREFIX_HEADS:
        return "prefix"
    if head.startswith("PRS") or head.startswith("SUFF"):
        return "suffix"
    return "stem"


def lcs_align(oshb, site):
    """Alineación LCS sobre `fold`. Devuelve lista de pasos:
    ('match', o, s) | ('extra', None, s) | ('missing', o, None)."""
    a = [t.fold for t in oshb]
    b = [t.fold for t in site]
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if a[i - 1] and a[i - 1] == b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    steps = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] and a[i - 1] == b[j - 1]:
            steps.append(("match", oshb[i - 1], site[j - 1]))
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            steps.append(("extra", None, site[j - 1]))
            j -= 1
        else:
            steps.append(("missing", oshb[i - 1], None))
            i -= 1
    steps.reverse()
    return steps


def new_heword(prefix_items, stem_item, suffix_item):
    """Construye un he_word a partir de morfemas OSHB (con es/gr re-mapeados)."""
    pf_forms = [p["form"] for p in prefix_items]
    pf_morphs = [p["morph"] for p in prefix_items]
    pf_es = [p["es"] for p in prefix_items]
    pf_gr = [p["gr"] for p in prefix_items]
    he_form = stem_item["form"] if stem_item else ""
    he_morph = stem_item["morph"] if stem_item else ""
    pref_uni = "".join(fold_he(f) for f in pf_forms)
    stem_uni = fold_he(he_form)
    suf_uni = fold_he(suffix_item["form"]) if suffix_item else ""
    hw = {
        "raw": "OSHB",
        "prefixes": [],
        "stem": "",
        "prefix_labels": [],
        "stem_label": "",
        "prefix_unicode": pref_uni,
        "stem_unicode": stem_uni,
        "full_unicode": pref_uni + stem_uni + suf_uni,
        "heb_label": "",
        "prefix_forms": pf_forms,
        "prefix_morphs": pf_morphs,
        "prefix_es": pf_es,
        "prefix_gr": pf_gr,
        "prefix_tier": ["" for _ in pf_forms],
        "he_form": he_form,
        "he_morph": he_morph,
        "strongs": stem_item["strongs"] if stem_item else "",
        "es": stem_item["es"] if stem_item else "",
        "gr_word": stem_item["gr"] if stem_item else "",
        "lxx_tier": "",
        "he_source": "oshb:restore",
    }
    if suffix_item:
        hw["prs_suffix"] = {
            "he_form": suffix_item["form"],
            "he_morph": suffix_item["morph"],
            "es": suffix_item["es"],
            "gr_word": suffix_item["gr"],
        }
    return hw


def build_hewords_for_pair(tokens):
    """tokens: lista ordenada de dict {form,morph,role,es,gr,strongs}.
    Agrupa por acumulación de prefijos -> stem (+suffix)."""
    hws = []
    cur_pref = []
    cur_stem = None
    cur_suffix = None

    def flush():
        nonlocal cur_pref, cur_stem, cur_suffix
        if cur_pref or cur_stem or cur_suffix:
            hws.append(new_heword(cur_pref, cur_stem, cur_suffix))
        cur_pref, cur_stem, cur_suffix = [], None, None

    for t in tokens:
        r = t["role"]
        if r == "prefix":
            if cur_stem is not None:
                flush()
            cur_pref.append(t)
        elif r == "stem":
            if cur_stem is not None:
                flush()
            cur_stem = t
        else:  # suffix
            if cur_stem is None:
                # sufijo huérfano -> trátalo como stem
                cur_stem = t
            elif cur_suffix is None:
                cur_suffix = t
            else:
                flush()
                cur_stem = t
    flush()
    return hws


def site_es_multiset(v):
    c = Counter()
    for t in list_site_tokens(v):
        e = (t.es or "").strip()
        if e:
            c[e] += 1
    return c


def site_gr_multiset(v):
    c = Counter()
    for t in list_site_tokens(v):
        g = (t.gr_word or "").strip()
        if g and g != "----":
            c[g] += 1
    return c


def _is_placeholder_es(g: str) -> bool:
    """Solo marca placeholders NO-curados (vacío, '[EN:...]' o compuesto inglés con
    punto). A diferencia de is_func_gloss, NO descarta palabras de función españolas
    ('a','en','por','y'): para 'lossless' esas también son contenido a preservar."""
    g2 = (g or "").strip().lower()
    if not g2:
        return True
    if g2.startswith("[en:"):
        return True
    if "." in g2 and all(c.isascii() for c in g2):
        return True
    return False


def verse_es_set(pairs):
    """Conjunto de valores español de un verso (excluye solo placeholders), leyendo
    TODOS los slots (prefijos + raíz + sufijo) de cada he_word. Espeja exactamente el
    medidor del gate del driver, para que 'lossless' coincida con la verificación."""
    s = set()
    for p in pairs:
        for hw in p.get("he_words", []):
            suff = hw.get("prs_suffix") or {}
            for e in list(hw.get("prefix_es") or []) + [hw.get("es") or ""] + [suff.get("es") or ""]:
                e = (e or "").strip()
                if e and not _is_placeholder_es(e):
                    s.add(e.lower())
    return s


def verse_gr_set(pairs):
    s = set()
    for p in pairs:
        for hw in p.get("he_words", []):
            suff = hw.get("prs_suffix") or {}
            for g in list(hw.get("prefix_gr") or []) + [hw.get("gr_word") or ""] + [suff.get("gr_word") or ""]:
                g = (g or "").strip()
                if g and g != "----":
                    s.add(g)
    return s


def _degarb_site(site):
    """Limpia el artefacto CATSS 'i>(' de las formas del sitio antes de alinear,
    para que no cause un falso 'missing'/gap. El texto final se reconstruye desde
    MT, así que esto solo afecta el emparejamiento y el rescate de glosas."""
    import dataclasses
    out = []
    for s in site:
        if "i>(" in (s.form or ""):
            cf = s.form.replace("i>(", "")
            out.append(dataclasses.replace(s, form=cf, fold=fold_he(cf)))
        else:
            out.append(s)
    return out


def rebuild_verse(v, ch, vs, source="oshb", slug="genesis", force=False):
    """Devuelve (new_pairs|None, info). None => omitir (sin tocar).
    force=True (modo web/TM): reconstruye también variantes (ignora protección de
    hueco) y fusiona glosas de contenido/griego huérfanas en el token vecino para
    no perder nada; las partículas de función huérfanas se sueltan (interlineal limpio)."""
    info = {"reason": "", "class": ""}
    oshb = src_tokens(source, slug, ch, vs)
    if not oshb:
        info["class"] = "no_oshb"
        return None, info
    site = _degarb_site(list_site_tokens(v))
    oshb_fold = src_concat_fold(source, slug, ch, vs)
    site_fold = fold_he(site_concatenated(v, False))
    if not oshb_fold:
        info["class"] = "no_oshb"
        return None, info
    if oshb_fold == site_fold:
        info["class"] = "already_ok"
        return None, info  # ya coincide: no tocar

    steps = lcs_align(oshb, site)

    # ── detección de huecos OSHB.
    # Un token "extra" con contenido (glosa/griego) cuyas consonantes NO existen
    # en OSHB => el propio OSHB está incompleto (p.ej. לו en 2:19, בו en 1:11).
    # No importa que se repita: si OSHB no tiene ese fold, NO lo borramos.
    # (Los duplicados genuinos tienen oshb_count>0 y sí se corrigen.)
    oshb_count = Counter(t.fold for t in oshb if t.fold)
    has_missing = any(kind == "missing" for kind, _, _ in steps)
    gap_tokens = []
    for kind, o, s in steps:
        if kind != "extra":
            continue
        has_content = bool((s.es or "").strip() or (s.gr_word or "").strip())
        if has_content and oshb_count[s.fold] == 0:
            gap_tokens.append(s)
    # Protección de hueco:
    #  - source=oshb (texto incompleto): cualquier contenido-extra que OSHB no
    #    trae se respeta (OSHB puede carecer de palabras del MT).
    #  - source=macula (MT completo): solo se protege cuando hay sustitución
    #    (algún token MT 'missing') = variante textual real (Ketiv/Qere). Si es
    #    inserción PURA (el sitio = MT + tokens de más, sin faltantes), esos
    #    extras son fragmentos/duplicados espurios del sitio y SÍ se eliminan.
    if gap_tokens and (has_missing or source != "macula") and not force:
        info["class"] = "oshb_gap"
        info["reason"] = ",".join(sorted(set(g.form for g in gap_tokens)))
        return None, info  # respeta hueco: deja verso intacto

    # ── pool de RESCATE: contenido de los tokens EXTRA (dobletes/espurios que
    # MT no trae). El token que ALINEA con MT conserva SU PROPIO es/gr/strongs
    # (es la glosa correcta, p.ej. 'voz' alineado a τῆς φωνῆς, no el doblete
    # 'sonido'). El pool solo rellena tokens FALTANTES o alineados-sin-glosa.
    rescue_pool = {}
    for kind, o, s in steps:
        if kind != "extra":
            continue
        if (s.es or "").strip() or (s.gr_word or "").strip() or (s.strongs or "").strip():
            rescue_pool.setdefault(s.fold, []).append(
                {"es": s.es or "", "gr": s.gr_word or "", "strongs": s.strongs or "",
                 "pair": getattr(s, "pair_idx", 0)})

    # ── asignar cada token OSHB a un par
    default_pair = 0
    for i, p in enumerate(v["pairs"]):
        if p.get("he_words"):
            default_pair = i
            break

    enriched = []   # dicts {pair, order, form, morph, role, fold, es, gr, strongs}
    last_pair = default_pair
    order = 0
    for kind, o, s in steps:
        if kind == "extra":
            continue  # token espurio del sitio -> se descarta (su contenido va al pool)
        if kind == "match":
            last_pair = s.pair_idx
            # conserva el contenido PROPIO del token alineado con MT
            enriched.append({"pair": s.pair_idx, "order": order, "form": o.form,
                             "morph": o.morph, "role": s.slot, "fold": o.fold,
                             "es": s.es or "", "gr": s.gr_word or "",
                             "strongs": s.strongs or ""})
        else:  # missing (MT trae morfema que el sitio no alineó) -> rellenar de pool
            enriched.append({"pair": last_pair, "order": order, "form": o.form,
                             "morph": o.morph, "role": role_of(o.morph), "fold": o.fold,
                             "es": "", "gr": "", "strongs": ""})
        order += 1

    # rescate por fold: solo a tokens SIN contenido propio (faltantes o alineados
    # vacíos). Se prefiere la copia con español no vacío, luego griego.
    def take_best(pool):
        for i, c in enumerate(pool):
            if (c["es"] or "").strip():
                return pool.pop(i)
        for i, c in enumerate(pool):
            if (c["gr"] or "").strip():
                return pool.pop(i)
        return pool.pop(0)

    # Pass 1: rellena tokens SIN ningún contenido propio.
    for tok in sorted(enriched, key=lambda t: (t["pair"], t["order"])):
        if (tok["es"] or "").strip() or (tok["gr"] or "").strip() or (tok["strongs"] or "").strip():
            continue  # ya tiene su contenido propio
        pool = rescue_pool.get(tok["fold"])
        if pool:
            c = take_best(pool)
            tok["es"], tok["gr"], tok["strongs"] = c["es"], c["gr"], c["strongs"]

    # Pass 2: UPGRADE — un token cuyo español es débil (vacío/función/placeholder)
    # adopta una glosa de CONTENIDO del mismo fold que quedó en el pool. Cubre el
    # caso de doblete donde el LCS conservó la copia con glosa pobre ('en') y
    # descartó la buena ('caminaron'); el griego propio del token se conserva.
    def _weak(es):
        return (not (es or "").strip()) or is_func_gloss(es)
    for tok in sorted(enriched, key=lambda t: (t["pair"], t["order"])):
        if not _weak(tok["es"]):
            continue
        pool = rescue_pool.get(tok["fold"])
        if not pool:
            continue
        for i, c in enumerate(pool):
            if (c["es"] or "").strip() and not is_func_gloss(c["es"]):
                chosen = pool.pop(i)
                tok["es"] = chosen["es"]
                if not (tok["gr"] or "").strip():
                    tok["gr"] = chosen["gr"]
                if not (tok["strongs"] or "").strip():
                    tok["strongs"] = chosen["strongs"]
                break

    # Pass 3: RESCATE GRIEGO — un token que quedó SIN gr_word adopta el griego (y
    # strongs) de un doblete del mismo fold que sobró en el pool. Cubre el caso donde
    # el superviviente ya tenía buen español ('todo') pero el enlace griego (πάντες,
    # κύριος, πρεσβύτας) viajaba en la copia descartada; así no se pierde alineación
    # griega. Estrictamente aditivo: nunca toca el español ni borra griego existente.
    for tok in sorted(enriched, key=lambda t: (t["pair"], t["order"])):
        if (tok["gr"] or "").strip():
            continue
        pool = rescue_pool.get(tok["fold"])
        if not pool:
            continue
        for i, c in enumerate(pool):
            if (c["gr"] or "").strip():
                chosen = pool.pop(i)
                tok["gr"] = chosen["gr"]
                if not (tok["strongs"] or "").strip():
                    tok["strongs"] = chosen["strongs"]
                break

    # Pass 4: FLUSH SIN PÉRDIDA — el contenido que sobró en el pool (dobletes que MT
    # colapsa, con griego repartido posicionalmente) se realoja para que NINGÚN valor
    # es/gr distinto del verso desaparezca. Para cada valor sobrante que YA NO esté
    # presente en el verso, se busca un token vacío que lo aloje: prioriza mismo fold,
    # luego mismo par, luego cualquiera. El griego nunca se borra; el español real solo
    # se reubica si su valor se perdería por completo. Es estrictamente conservador.
    def _present_es():
        return {(t["es"] or "").strip().lower() for t in enriched if (t["es"] or "").strip()}
    def _present_gr():
        return {(t["gr"] or "").strip() for t in enriched if (t["gr"] or "").strip()}
    def _host(field, fold_key, pair_idx):
        order_iter = sorted(enriched, key=lambda t: (t["pair"], t["order"]))
        for want_fold, want_pair in ((True, True), (True, False), (False, True), (False, False)):
            for t in order_iter:
                if (t[field] or "").strip():
                    continue
                if want_fold and t["fold"] != fold_key:
                    continue
                if want_pair and t["pair"] != pair_idx:
                    continue
                return t
        return None
    leftovers = [(fk, c) for fk, pool in rescue_pool.items() for c in pool]
    for fk, c in leftovers:
        gr = (c.get("gr") or "").strip()
        es = (c.get("es") or "").strip()
        pair_idx = c.get("pair", default_pair)
        if gr and gr not in _present_gr():
            h = _host("gr", fk, pair_idx)
            if h is not None:
                h["gr"] = gr
                if not (h["strongs"] or "").strip() and (c.get("strongs") or "").strip():
                    h["strongs"] = c["strongs"]
        if es and not is_func_gloss(es) and es.lower() not in _present_es():
            h = _host("es", fk, pair_idx)
            if h is not None:
                h["es"] = es

    # Pass 5: FUSIÓN FORZADA (solo modo force/web). Lo que aún no halló hueco vacío se
    # fusiona en el último token de su par para NO perder contenido ni griego; las
    # partículas de función huérfanas se sueltan (interlineal limpio en la web).
    if force:
        def _merge_host(pair_idx):
            cand = [t for t in enriched if t["pair"] == pair_idx] or enriched
            return cand[-1] if cand else None
        for fk, c in leftovers:
            gr = (c.get("gr") or "").strip()
            es = (c.get("es") or "").strip()
            pair_idx = c.get("pair", default_pair)
            if gr and gr not in _present_gr():
                h = _merge_host(pair_idx)
                if h is not None:
                    h["gr"] = (h["gr"] + " " + gr).strip() if (h["gr"] or "").strip() else gr
            if es and not is_func_gloss(es) and es.lower() not in _present_es():
                h = _merge_host(pair_idx)
                if h is not None:
                    h["es"] = (h["es"] + " · " + es).strip() if (h["es"] or "").strip() else es

    # agrupa por par (en orden de aparición OSHB)
    per_pair = {}
    for tok in enriched:
        per_pair.setdefault(tok["pair"], []).append(tok)

    # ── construir nuevos pares: conserva todo, solo reemplaza he_words/he_*
    new_pairs = []
    for i, p in enumerate(v["pairs"]):
        np = copy.deepcopy(p)
        toks = per_pair.get(i, [])
        if p.get("kind") == "gk_add":
            # par solo-griego: no debe llevar hebreo; conserva tal cual
            new_pairs.append(np)
            continue
        new_hws = build_hewords_for_pair(toks) if toks else []
        np["he_words"] = new_hws
        # recompone campos hebreos a nivel par
        full = "".join(h.get("full_unicode", "") for h in new_hws)
        np["he_unicode"] = "".join(
            "".join(h.get("prefix_forms", [])) + (h.get("he_form") or "")
            + ((h.get("prs_suffix") or {}).get("he_form", ""))
            for h in new_hws)
        np["he_stem_unicode"] = full
        new_pairs.append(np)

    # ── verificación dura: texto consonántico == OSHB
    new_fold = "".join(
        fold_he("".join(h.get("prefix_forms", [])) + (h.get("he_form") or "")
                + ((h.get("prs_suffix") or {}).get("he_form", "")))
        for p in new_pairs for h in p.get("he_words", []))
    if new_fold != oshb_fold:
        info["class"] = "unresolved"
        info["reason"] = "no se alcanzó OSHB exacto tras reconstrucción"
        return None, info

    # ── RED DE SEGURIDAD (solo force): garantiza CERO pérdida de griego ni de
    # español-contenido. Opera sobre la estructura FINAL (la misma que mide el gate):
    # cualquier valor presente ANTES que ya no esté (ni como token ni como subcadena)
    # se fusiona en el último token del verso. Las partículas de función no se
    # reinyectan (interlineal limpio para la web). Es la última línea de defensa por si
    # los Passes 1-5 dejaron algo fuera al reagrupar morfemas (prefijo/raíz/sufijo).
    if force:
        def _last_hw():
            for p in reversed(new_pairs):
                hws = p.get("he_words") or []
                if hws:
                    return hws[-1]
            return None
        # GRIEGO: cualquier gr presente antes que ya no esté (ni como subcadena) se
        # fusiona en el gr_word del último token; nunca se pierde un enlace LXX.
        after_gr = verse_gr_set(new_pairs)
        after_gr_blob = " || ".join(after_gr)
        for g in verse_gr_set(v["pairs"]):
            if g in after_gr or g in after_gr_blob:
                continue
            hw = _last_hw()
            if hw is not None:
                cur = (hw.get("gr_word") or "").strip()
                hw["gr_word"] = (cur + " " + g).strip() if (cur and cur != "----") else g
                after_gr_blob += " || " + g
        # ESPAÑOL-CONTENIDO: igual, con CASO ORIGINAL (preserva mayúsculas de nombres).
        # Si el token host tiene es vacío o placeholder ('[EN:...]'), se REEMPLAZA (no se
        # antepone el placeholder, que volvería invisible el valor al medirse).
        after_es_low = {x.lower() for x in verse_es_set(new_pairs)}
        after_es_blob = " || ".join(after_es_low)
        seen = set()
        for p in v["pairs"]:
            for hw0 in p.get("he_words", []):
                suff0 = hw0.get("prs_suffix") or {}
                for raw in list(hw0.get("prefix_es") or []) + [hw0.get("es") or ""] + [suff0.get("es") or ""]:
                    raw = (raw or "").strip()
                    if not raw or _is_placeholder_es(raw) or is_func_gloss(raw):
                        continue
                    low = raw.lower()
                    if low in seen or low in after_es_low or low in after_es_blob:
                        continue
                    seen.add(low)
                    hw = _last_hw()
                    if hw is not None:
                        cur = (hw.get("es") or "").strip()
                        if not cur or _is_placeholder_es(cur):
                            hw["es"] = raw
                        else:
                            hw["es"] = cur + " · " + raw
                        after_es_blob += " || " + low

    info["class"] = "fixed"
    return new_pairs, info


def run(apply: bool, limit_ch=None, mode="strict", source="oshb", slug="genesis"):
    strict = mode == "strict"
    set_active_book(slug)
    cfg = resolve(slug)
    data = load_active()

    stats = Counter()
    es_lost_total = 0
    changed = []
    samples_fixed, samples_gap, samples_unres, samples_esloss = [], [], [], []
    gap_rows, esloss_rows = [], []

    for v in data["verses"]:
        try:
            ch, vs = parse_ref(verse_ref(v))
        except Exception:
            stats["bad_ref"] += 1
            continue
        if limit_ch is not None and ch != limit_ch:
            continue

        gr_before = [(pp.get("gr_unicode") or "") for pp in v["pairs"]]
        es_before = site_es_multiset(v)
        es_before_set = verse_es_set(v["pairs"])
        gr_before_set = verse_gr_set(v["pairs"])

        new_pairs, info = rebuild_verse(v, ch, vs, source, slug, force=(mode == "force"))
        stats[info["class"]] += 1

        if new_pairs is None:
            if info["class"] == "oshb_gap":
                gap_rows.append((ch, vs, info["reason"]))
                if len(samples_gap) < 12:
                    samples_gap.append((ch, vs, info["reason"]))
            if info["class"] == "unresolved" and len(samples_unres) < 12:
                samples_unres.append((ch, vs))
            continue

        # candado griego
        gr_after = [(pp.get("gr_unicode") or "") for pp in new_pairs]
        if gr_after != gr_before:
            stats["GR_VIOLATION"] += 1
            continue

        # español conservado: pérdida REAL = glosa que desaparece del todo
        tmp = {"pairs": new_pairs}
        es_after = site_es_multiset(tmp)
        dup_removed = es_before - es_after          # incluye duplicados
        true_lost = {g: c for g, c in dup_removed.items() if es_after.get(g, 0) == 0}
        n_true = sum(true_lost.values())
        n_dup = sum(dup_removed.values()) - n_true
        es_lost_total += n_true
        if n_true:
            stats["verses_es_loss"] += 1

        # modo lossless: NINGÚN valor es/gr distinto puede desaparecer del verso.
        # Reconstruye solo versos perfectamente conservadores (gana coincidencia TM
        # sin tocar griego/español); deja intactos los versos con cualquier pérdida.
        # Mide por CONJUNTO de valores leyendo todos los slots (= medidor del gate).
        if mode == "lossless":
            es_gone = es_before_set - verse_es_set(new_pairs)
            gr_gone = gr_before_set - verse_gr_set(new_pairs)
            if es_gone or gr_gone:
                stats["lossless_skip"] += 1
                continue

        if n_true:
            esloss_rows.append((ch, vs, true_lost, {}))
            if len(samples_esloss) < 20:
                samples_esloss.append((ch, vs, true_lost))
            has_content_loss = any(not is_func_gloss(g) for g in true_lost)
            if has_content_loss:
                stats["content_loss"] += 1
            else:
                stats["func_loss_only"] += 1
            if mode == "strict":
                stats["es_loss_skip"] += 1
                continue   # candado absoluto: no tocar versos que pierden glosa
            if mode == "nocontent" and has_content_loss:
                stats["es_loss_skip"] += 1
                continue   # permite función/placeholder, nunca contenido
        else:
            stats["fixed_no_loss"] += 1
        if len(samples_fixed) < 14:
            samples_fixed.append((ch, vs, len(v["pairs"]), n_dup, n_true))
        changed.append((v, new_pairs))

    # ── reporte
    print("=" * 64)
    print(f"{slug.upper()}  ·  fuente={source}  ·  modo={'APPLY' if apply else 'DRY-RUN'}"
          + (f"  cap={limit_ch}" if limit_ch else ""))
    print("=" * 64)
    print(f"  fixed (reconstruidos a OSHB) : {stats['fixed']}")
    print(f"  already_ok (ya coincidían)   : {stats['already_ok']}")
    print(f"  oshb_gap (hueco OSHB, omito) : {stats['oshb_gap']}")
    print(f"  unresolved (no llegó a OSHB) : {stats['unresolved']}")
    print(f"  no_oshb                      : {stats['no_oshb']}")
    print(f"  GR_VIOLATION (descartado)    : {stats['GR_VIOLATION']}")
    print(f"  glosas ES pérdida REAL       : {es_lost_total}  (en {stats['verses_es_loss']} versos)")
    print(f"  modo={mode}  |  versos sin pérdida ES : {stats['fixed_no_loss']}")
    print(f"  versos que pierden SOLO función/placeholder : {stats['func_loss_only']}")
    print(f"  versos que pierden CONTENIDO                : {stats['content_loss']}")
    print(f"  versos OMITIDOS por política                : {stats['es_loss_skip']}")
    if stats['lossless_skip']:
        print(f"  versos OMITIDOS por lossless (pérdida es/gr): {stats['lossless_skip']}")
    print()
    print("-- ejemplos FIXED (ch:vs, #pares, dup_glosa_quitada, es_perdida_real) --")
    for s in samples_fixed:
        print(f"  {s[0]}:{s[1]}  pares={s[2]}  dup_quitado={s[3]}  es_real_perdido={s[4]}")
    print("\n-- versos con PÉRDIDA REAL de español (revisar) --")
    for s in samples_esloss:
        print(f"  {s[0]}:{s[1]}  ->  {s[2]}")
    print("\n-- ejemplos OSHB_GAP (omitidos, hueco en OSHB) --")
    for s in samples_gap:
        print(f"  {s[0]}:{s[1]}  ->  {s[2]}")
    print("\n-- ejemplos UNRESOLVED (omitidos) --")
    for s in samples_unres:
        print(f"  {s[0]}:{s[1]}")

    # ── resumen antes/después + CSVs
    total = stats["fixed"] + stats["already_ok"] + stats["oshb_gap"] + stats["unresolved"]
    ok_before = stats["already_ok"]
    ok_after = stats["already_ok"] + len(changed)   # solo lo realmente aplicable
    if total:
        print("\n" + "-" * 64)
        print(f"  COINCIDENCIA OSHB  antes: {ok_before}/{total} ({100*ok_before/total:.1f}%)"
              f"   ->  después: {ok_after}/{total} ({100*ok_after/total:.1f}%)")
        print(f"  (los {stats['oshb_gap']} 'oshb_gap' siguen sin coincidir porque OSHB"
              f" está incompleto, no por el sitio)")

    if not apply:
        rep = Path("data/_hebrew_reports")
        rep.mkdir(parents=True, exist_ok=True)
        with (rep / "genesis_es_loss.csv").open("w", encoding="utf-8") as f:
            f.write("ch,vs,glosa,veces,fold_en_oshb\n")
            for ch, vs, lost, foldinfo in esloss_rows:
                for g, c in lost.items():
                    f.write(f"{ch},{vs},{g},{c},{foldinfo.get(g,'?')}\n")
        with (rep / "genesis_oshb_gap.csv").open("w", encoding="utf-8") as f:
            f.write("ch,vs,formas_que_OSHB_no_trae\n")
            for ch, vs, forms in gap_rows:
                f.write(f"{ch},{vs},{forms}\n")
        print(f"\nReportes CSV en {rep}/  (genesis_es_loss.csv, genesis_oshb_gap.csv)")

    if apply and changed:
        src = Path(cfg.final_json_path)
        bdir = Path("data/_hebrew_backup")
        bdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(src, bdir / f"{slug}_final.PREHEB_apply.{source}.{ts}.json")
        for v, new_pairs in changed:
            v["pairs"] = new_pairs
        src.write_text(json.dumps(data, ensure_ascii=False,
                                  separators=(",", ":")), encoding="utf-8")
        print(f"\nAPLICADO. {len(changed)} versos escritos. Respaldo en {bdir}")
    elif apply:
        print("\nNada que aplicar.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--mode", choices=["strict", "nocontent", "aggressive", "lossless", "force"],
                    default="strict",
                    help="lossless=cero pérdida de valores es/gr por verso; "
                         "strict=sin pérdida de glosa es; nocontent=permite función/placeholder; "
                         "aggressive=aplica todo")
    ap.add_argument("--source", choices=["oshb", "macula"], default="oshb",
                    help="fuente de verdad hebrea (macula = MT completo)")
    ap.add_argument("--book", default="genesis")
    args = ap.parse_args()
    run(args.apply, args.chapter, args.mode, args.source, args.book)
