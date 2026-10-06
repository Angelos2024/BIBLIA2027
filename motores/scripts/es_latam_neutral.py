"""
es_latam_neutral.py — Español peninsular → latino/neutro (Global Pass 17).

Convierte glosas y textos corrido en:
  - <libro>_final.json (es, prefix_es, prs_suffix.es, es_gloss)
  - rv1960_<libro>.json (si existe)
  - glosas_personales.json (after.es / before.es opcional)

Orden de aplicación:
  1. Frases compuestas (con vosotros → con ustedes, …)
  2. Léxico peninsular (solo palabras completas)
  3. Pronombres y posesivos (palabra completa)
  4. Verbos irregulares (tabla cerrada)
  5. Imperativos (tabla cerrada)
  6. Terminaciones verbales acentuadas (mín. 3 letras de raíz)

Seguridad anti-deformación:
  - Lista _FROZEN_WORDS: país, reis, mais, Dios, etc. nunca se tocan
  - Sin reglas -ais/-eis sin acento (evita pais→pan, reis→ren)
  - Futuro -réis/-eréis/-iréis antes que presente -éis
  - «que deis» → «que den» solo en frase, no «deis» suelto
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ── 1. Frases (más largas primero) ───────────────────────────────────────────
_PHRASES: list[tuple[str, str]] = [
    (r"\bde\s+vosotros\b", "de ustedes"),
    (r"\bde\s+vosotras\b", "de ustedes"),
    (r"\bpara\s+vosotros\b", "para ustedes"),
    (r"\bpara\s+vosotras\b", "para ustedes"),
    (r"\bcon\s+vosotros\b", "con ustedes"),
    (r"\bcon\s+vosotras\b", "con ustedes"),
    (r"\ba\s+vosotros\b", "a ustedes"),
    (r"\ba\s+vosotras\b", "a ustedes"),
    (r"\bhacia\s+vosotros\b", "hacia ustedes"),
    (r"\bentre\s+vosotros\b", "entre ustedes"),
    (r"\bsobre\s+vosotros\b", "sobre ustedes"),
    (r"\bno\s+os\s+preocup[eé]is\b", "no se preocupen"),
    (r"\bdaos\s+prisa\b", "dense prisa"),
    (r"\bdaos\s+cuenta\b", "dense cuenta"),
    (r"\bpon[eé]os\s+c[oó]modos\b", "pónganse cómodos"),
    (r"\bpon[eé]os\b", "pónganse"),
    (r"\bsentaos\b", "siéntense"),
    (r"\blevantaos\b", "levántense"),
    (r"\bcallaos\b", "cállense"),
    (r"\bmarchaos\b", "váyanse"),
    (r"\bacordaos\b", "acuérdense"),
    (r"\bos\s+lo\b", "se lo"),
    (r"\bos\s+la\b", "se la"),
    (r"\bos\s+los\b", "se los"),
    (r"\bos\s+las\b", "se las"),
    (r"\bos\s+el\b", "se lo"),
    (r"\bos\s+le\b", "se le"),
    (r"\bos\s+les\b", "se les"),
    (r"\bqu[eé]\s+tal\s+est[aá]is\b", "cómo están"),
    (r"\bquer[eé]is\s+venir\b", "quieren venir"),
    (r"\bos\s+parece\b", "les parece"),
    (r"\bos\s+lo\s+dije\b", "se lo dije"),
    (r"\bos\s+lo\s+enviar[eé]\b", "se lo enviaré"),
    (r"\bos\s+lo\s+he\s+dicho\b", "se lo he dicho"),
    (r"\bhab[eé]is\s+terminado\b", "han terminado"),
    (r"\bhab[eé]is\s+visto\b", "han visto"),
    (r"\bhab[eé]is\s+hecho\b", "han hecho"),
    (r"\bhab[eé]is\s+sido\b", "han sido"),
    (r"\bid\s+con\s+cuidado\b", "vayan con cuidado"),
    (r"\bvenid\s+aqu[ií]\b", "vengan aquí"),
    (r"\bcoger\s+el\s+autob[uú]s\b", "tomar el bus"),
    (r"\bcoger\s+una\s+llamada\b", "atender una llamada"),
    (r"\bhacer\s+cola\b", "hacer fila"),
    (r"\ben\s+paro\b", "desempleado"),
    (r"\bes\s+vuestra\b", "es de ustedes"),
    (r"\bes\s+vuestro\b", "es de ustedes"),
    (r"\bes\s+vuestros\b", "es de ustedes"),
    (r"\bes\s+vuestras\b", "es de ustedes"),
    (r"\bque\s+deis\b", "que den"),
]

# ── 2. Pronombres / posesivos (palabra completa) ─────────────────────────────
_WORD_MAP: dict[str, str] = {
    "vosotros": "ustedes",
    "vosotras": "ustedes",
    "Vosotros": "Ustedes",
    "Vosotras": "Ustedes",
    "VOSOTROS": "USTEDES",
    "VOSOTRAS": "USTEDES",
    "vuestro": "su",
    "vuestra": "su",
    "vuestros": "sus",
    "vuestras": "sus",
    "Vuestro": "Su",
    "Vuestra": "Su",
    "Vuestros": "Sus",
    "Vuestras": "Sus",
    # os suelto → les (obj. indirecto; la mayoría en texto bíblico)
    "os": "les",
    "Os": "Les",
    "OS": "LES",
}

# ── 3. Verbos irregulares 2ª pl → 3ª pl ─────────────────────────────────────
_VERB_IRREG: dict[str, str] = {
    "sois": "son",
    "estáis": "están",
    "estais": "están",
    "vais": "van",
    "habéis": "han",
    "habeis": "han",
    "veis": "ven",
    "dais": "dan",
    "sabéis": "saben",
    "sabeis": "saben",
    "hacéis": "hacen",
    "haceis": "hacen",
    "decís": "dicen",
    "decis": "dicen",
    "queréis": "quieren",
    "quereis": "quieren",
    "podéis": "pueden",
    "podeis": "pueden",
    "tenéis": "tienen",
    "teneis": "tienen",
    "venís": "vienen",
    "venis": "vienen",
    "oís": "oyen",
    "ois": "oyen",
    "moriréis": "morirán",
    "morireis": "morirán",
    "moriríais": "morirían",
    "moririais": "morirían",
    "muriereis": "murieran",
    "muriéreis": "murieran",
    "obedecéis": "obedecen",
    "obedeceis": "obedecen",
    "comeréis": "comerán",
    "comereis": "comerán",
    "comeríais": "comerían",
    "comeriais": "comerían",
    "viviréis": "vivirán",
    "vivireis": "vivirán",
    "hablaréis": "hablarán",
    "hablareis": "hablarán",
    "hablaríais": "hablarían",
    "hablariais": "hablarían",
    "fuisteis": "fueron",
    "visteis": "vieron",
    "hicisteis": "hicieron",
    "dijisteis": "dijeron",
    "vinisteis": "vinieron",
    "iréis": "irán",
    "ireis": "irán",
    "vendréis": "vendrán",
    "vendreis": "vendrán",
    "haréis": "harán",
    "hareis": "harán",
    "diréis": "dirán",
    "direis": "dirán",
    "podréis": "podrán",
    "podreis": "podrán",
    "tendréis": "tendrán",
    "tendreis": "tendrán",
    "seréis": "serán",
    "sereis": "serán",
    "estaréis": "estarán",
    "estareis": "estarán",
    "estabais": "estaban",
    "erais": "eran",
    "teníais": "tenían",
    "teniais": "tenían",
    "podíais": "podían",
    "podiais": "podían",
    "sabríais": "sabrían",
    "sabriais": "sabrían",
    "estaríais": "estarían",
    "estariais": "estarían",
    "comisteis": "comieron",
    "comíais": "comían",
    "comiais": "comían",
    "hablabais": "hablaban",
    "hablasteis": "hablaron",
    "habláis": "hablan",
    "hablais": "hablan",
    "coméis": "comen",
    "comeis": "comen",
    "vivís": "viven",
    "vivis": "viven",
    "obedeceréis": "obedecerán",
    "obedecereis": "obedecerán",
    "caeréis": "caerán",
    "caereis": "caerán",
    "leeréis": "leerán",
    "leereis": "leerán",
    "creeréis": "creerán",
    "creereis": "creerán",
    "veréis": "verán",
    "vereis": "verán",
    "oiréis": "oirán",
    "oireis": "oirán",
    "confiáis": "confían",
    "confiais": "confían",
}

# ── 4. Imperativos ───────────────────────────────────────────────────────────
_IMPERATIVE: dict[str, str] = {
    "hablad": "hablen",
    "mirad": "miren",
    "escuchad": "escuchen",
    "comed": "coman",
    "bebed": "beban",
    "vivid": "vivan",
    "venid": "vengan",
    "id": "vayan",
    "decid": "digan",
    "haced": "hagan",
    "tened": "tengan",
    "poned": "pongan",
    "salid": "salgan",
    "Hablad": "Hablen",
    "Comed": "Coman",
    "Vivid": "Vivan",
    "Venid": "Vengan",
    "Id": "Vayan",
    "Decid": "Digan",
    "Haced": "Hagan",
}

# ── 5. Terminaciones verbales (solo formas acentuadas; sin -ais/-eis sueltos) ─
# Orden: futuro/condicional → pretérito → imperfecto → presente
_VERB_SUFFIX: list[tuple[str, str]] = [
    (r"(\w{3,})aréis\b", r"\1arán"),
    (r"(\w{3,})eréis\b", r"\1erán"),
    (r"(\w{3,})iréis\b", r"\1irán"),
    (r"(\w{3,})réis\b", r"\1rán"),       # caeréis, leeréis, veréis
    (r"(\w{3,})aríais\b", r"\1arían"),
    (r"(\w{3,})eríais\b", r"\1erían"),
    (r"(\w{3,})iríais\b", r"\1irían"),
    (r"(\w{3,})asteis\b", r"\1aron"),
    (r"(\w{3,})isteis\b", r"\1ieron"),
    (r"(\w{3,})abais\b", r"\1aban"),
    (r"(\w{3,})íais\b", r"\1ían"),
    (r"(\w{3,})áis\b", r"\1an"),
    (r"(\w{3,})éis\b", r"\1en"),
    (r"(\w{3,})ís\b", r"\1en"),
]

# ── 6. Léxico peninsular ─────────────────────────────────────────────────────
# DESACTIVADO para el corpus bíblico. Este léxico era vocabulario MODERNO de
# España→Latam (ordenador→computadora, móvil→celular, coche→carro,
# mando→«control remoto», zumo→jugo, patata→papa, coger→tomar…). Nada de eso
# aparece en la Escritura y, peor aún, varios «orígenes» son HOMÓGRAFOS de
# palabras bíblicas reales que provocaban corrupción de datos:
#   · «mando»  = verbo (yo mando/ordeno, צוה)     → se convertía en «control remoto»
#   · «piso»   = verbo (yo piso/huello el lagar)  → «apartamento»
#   · «vale»   = verbo (valer)                    → «está bien»
#   · «grifo», «coger», «conducir», «billete»…    → falsos positivos
# La conversión peninsular→latino LEGÍTIMA (vosotros→ustedes, terminaciones
# verbales -áis/-éis/-asteis…, imperativos «Haced»→«Hagan», «os»→«les»,
# «vuestro»→«su») vive en _VERB_SUFFIX / _VERB_IRREG / _IMPERATIVE / _PHRASES y
# sigue activa. Si algún día se necesita un léxico, debe ser específico y con
# guardas de homógrafo, NO esta lista de coloquialismos modernos.
_LEXICON: dict[str, str] = {}

# Palabras que nunca deben transformarse (sustantivos, nombres, falsos positivos)
_FROZEN_WORDS = frozenset({
    "pais", "país", "paises", "países", "paraiso", "paraíso",
    "dios", "jehová", "jehova", "hashem", "yahweh", "yahvé",
    "reyes", "reis", "mais", "deis", "atlas", "crisis", "análisis", "analisis",
    "lunes", "martes", "jueves", "viernes", "génesis", "genesis", "exodo", "éxodo",
    "nos", "dos", "sos", "mas", "más", "gloria", "historia", "memoria",
    "seria", "sería", "escoger", "salvador", "validé", "valide", "lapis",
    "avis", "asis", "misis", "this",
})


def _is_frozen(word: str) -> bool:
    return word.lower() in _FROZEN_WORDS


def _apply_phrases(text: str) -> str:
    for pat, repl in _PHRASES:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    return text


def _apply_word_map(text: str) -> str:
    def repl(m: re.Match) -> str:
        w = m.group(0)
        return _WORD_MAP.get(w, _WORD_MAP.get(w.lower(), w))

    words = "|".join(re.escape(k) for k in sorted(_WORD_MAP, key=len, reverse=True))
    return re.sub(rf"\b({words})\b", repl, text)


def _apply_lexicon(text: str) -> str:
    for src, dst in sorted(_LEXICON.items(), key=lambda x: -len(x[0])):
        text = re.sub(rf"\b{re.escape(src)}\b", dst, text, flags=re.IGNORECASE)
    return text


def _apply_verb_irreg_word(word: str) -> str:
    if _is_frozen(word):
        return word
    low = word.lower()
    if low in _VERB_IRREG:
        rep = _VERB_IRREG[low]
        if word.isupper():
            return rep.upper()
        if word[0].isupper():
            return rep[0].upper() + rep[1:]
        return rep
    if word in _IMPERATIVE:
        return _IMPERATIVE[word]
    low_imp = word.lower()
    if low_imp in _IMPERATIVE:
        rep = _IMPERATIVE[low_imp]
        if word.isupper():
            return rep.upper()
        if word[0].isupper():
            return rep[0].upper() + rep[1:]
        return rep
    return word


def _apply_verb_suffixes(word: str) -> str:
    if _is_frozen(word):
        return word
    if word.lower() in _VERB_IRREG or word.lower() in _IMPERATIVE:
        return word
    orig = word
    w = word
    for pat, repl in _VERB_SUFFIX:
        nw = re.sub(pat, repl, w, flags=re.IGNORECASE)
        if nw != w:
            w = nw
            break
    if w != orig:
        if orig.isupper():
            return w.upper()
        if orig[0].isupper():
            return w[0].upper() + w[1:]
        return w
    return orig


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"\S+|\s+", text)


def to_latam_neutral(text: str) -> str:
    """Convierte una cadena de español peninsular a latino/neutro."""
    if not text or not str(text).strip():
        return text
    s = str(text)
    s = _apply_phrases(s)
    s = _apply_lexicon(s)
    s = _apply_word_map(s)
    parts = re.split(r"(\b[\w\u00C0-\u024F]+\b)", s)
    out: list[str] = []
    for part in parts:
        if re.fullmatch(r"[\w\u00C0-\u024F]+", part or ""):
            w = _apply_verb_irreg_word(part)
            w = _apply_verb_suffixes(w)
            out.append(w)
        else:
            out.append(part)
    return "".join(out)


def _set_if_changed(obj: dict, key: str, new_val: str) -> bool:
    old = (obj.get(key) or "").strip()
    new = (new_val or "").strip()
    if not new or new == old:
        return False
    obj[key] = new_val
    return True


def apply_to_interlineal(data: dict) -> dict[str, int]:
    stats = {"stem_es": 0, "prefix_es": 0, "prs_suffix_es": 0, "pair_es_gloss": 0}
    for verse in data.get("verses", []):
        for pair in verse.get("pairs", []):
            if _set_if_changed(pair, "es_gloss", to_latam_neutral(pair.get("es_gloss") or "")):
                stats["pair_es_gloss"] += 1
            for hw in pair.get("he_words", []):
                if _set_if_changed(hw, "es", to_latam_neutral(hw.get("es") or "")):
                    stats["stem_es"] += 1
                pes = hw.get("prefix_es") or []
                for i, pe in enumerate(pes):
                    new = to_latam_neutral(pe)
                    if new != (pe or "").strip():
                        pes[i] = new
                        stats["prefix_es"] += 1
                prs = hw.get("prs_suffix")
                if isinstance(prs, dict) and _set_if_changed(
                    prs, "es", to_latam_neutral(prs.get("es") or "")
                ):
                    stats["prs_suffix_es"] += 1
    return stats


def apply_to_rv1960(rv_data: list) -> dict[str, int]:
    stats = {"verses": 0}
    for ci, chapter in enumerate(rv_data):
        if not isinstance(chapter, list):
            continue
        for vi, text in enumerate(chapter):
            new = to_latam_neutral(text or "")
            if new != (text or "").strip():
                rv_data[ci][vi] = new
                stats["verses"] += 1
    return stats


def apply_to_glossas_registry(registry: dict) -> dict[str, int]:
    stats = {"rules": 0}
    for bucket in ("global", "contexto"):
        for rule in registry.get(bucket, []):
            changed = False
            for side in ("before", "after"):
                block = rule.get(side) or {}
                if "es" in block:
                    new = to_latam_neutral(block.get("es") or "")
                    if new != (block.get("es") or "").strip():
                        block["es"] = new
                        changed = True
            if changed:
                stats["rules"] += 1
    return stats


def apply_latam_to_book(
    book: str,
    *,
    data_dir: Path,
    include_rv: bool = True,
    include_glossas: bool = True,
) -> dict[str, Any]:
    """Aplica conversión latina a todos los JSON del libro."""
    final_path = data_dir / f"{book}_final.json"
    if not final_path.exists():
        raise FileNotFoundError(final_path)

    data = json.loads(final_path.read_text(encoding="utf-8"))
    result: dict[str, Any] = {"book": book, "interlineal": apply_to_interlineal(data)}

    final_path.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    if include_rv:
        rv_path = data_dir / f"rv1960_{book}.json"
        if rv_path.exists():
            rv = json.loads(rv_path.read_text(encoding="utf-8"))
            result["rv1960"] = apply_to_rv1960(rv)
            rv_path.write_text(
                json.dumps(rv, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

    if include_glossas:
        gloss_path = data_dir / "glosas_personales.json"
        if gloss_path.exists():
            reg = json.loads(gloss_path.read_text(encoding="utf-8"))
            result["glosas"] = apply_to_glossas_registry(reg)
            gloss_path.write_text(
                json.dumps(reg, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )

    result["total"] = sum(
        v for k, v in result.get("interlineal", {}).items()
    ) + sum(v for k, v in result.get("rv1960", {}).items()) + sum(
        v for k, v in result.get("glosas", {}).items()
    )
    return result
