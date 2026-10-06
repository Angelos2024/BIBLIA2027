# -*- coding: utf-8 -*-
"""Compact Genesis 1–10 payload for the C4 layer prototype."""
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(r"C:\Users\Angelos\Desktop\BIBLIA2027")
OUT = ROOT / "septuaginta" / "samaritan_tal_florentin"

TEAMIM = set(range(0x0591, 0x05B0)) | {0x05C0, 0x05C3, 0x05C4, 0x05C5, 0x05C6}
NIQQUD = set(range(0x05B0, 0x05BD)) | {0x05BF, 0x05C1, 0x05C2, 0x05C7}

ES_PROCLITICS = {
    "lo", "la", "los", "las", "le", "les", "me", "te", "nos", "os", "se",
    "su", "mi", "tu", "sus", "mis", "tus",
}


def clean_he(s: str) -> str:
    if not s:
        return ""
    return "".join(ch for ch in s if ord(ch) not in TEAMIM).replace("\u05c0", "").strip()


def cons(s: str) -> str:
    s = clean_he(s)
    return "".join(ch for ch in s if ord(ch) not in NIQQUD and ch not in "־-–")


def combine_es(stem, suf, morph=""):
    if not suf:
        return stem or ""
    if not stem:
        return suf
    s = suf.lower().strip()
    if s in stem.lower().split():
        return stem
    if s in ES_PROCLITICS:
        return f"{suf} {stem}"
    return f"{stem} {suf}"


def emit_pair(pair):
    toks = []
    if pair.get("kind") == "gk_add":
        toks.append({
            "k": "add",
            "he": "",
            "morph": "ADD",
            "es": "—",
            "gr": (pair.get("gr_unicode") or "").strip(),
        })
        return toks
    if pair.get("kind") == "heb_omit":
        he = clean_he(pair.get("he_unicode") or "")
        toks.append({"k": "omit", "he": he, "morph": "—", "es": "—", "gr": ""})
        return toks
    for hw in pair.get("he_words") or []:
        pforms = hw.get("prefix_forms") or []
        pes = hw.get("prefix_es") or []
        pmorph = hw.get("prefix_morphs") or []
        pgr = hw.get("prefix_gr") or []
        for i, pf in enumerate(pforms):
            es = (pes[i] if i < len(pes) else "") or ""
            if not clean_he(pf) and not es.strip():
                continue
            toks.append({
                "k": "pre",
                "he": clean_he(pf),
                "morph": (pmorph[i] if i < len(pmorph) else "") or "PREP/CONJ",
                "es": es,
                "gr": (pgr[i] if i < len(pgr) else "") or "",
                "cons": cons(pf),
            })
        form = clean_he(hw.get("he_form") or hw.get("stem_unicode") or "")
        suf = hw.get("prs_suffix") or {}
        suf_he = clean_he(suf.get("he_form") or "")
        suf_es = (suf.get("es") or "").strip()
        morph = hw.get("he_morph") or ""
        if suf.get("he_morph"):
            morph = f"{morph} + {suf['he_morph']}" if morph else suf["he_morph"]
        es = combine_es(hw.get("es") or "", suf_es, morph)
        gr = hw.get("gr_word") or ""
        if suf.get("gr_word"):
            gr = (gr + " " + suf["gr_word"]).strip()
        if not form and not es and not gr:
            continue
        toks.append({
            "k": "he",
            "he": form + suf_he,
            "morph": morph,
            "es": es,
            "gr": gr,
            "cons": cons(form + suf_he),
        })
    return toks


def lxx_line(pairs):
    parts = []
    for p in pairs:
        g = (p.get("gr_unicode") or "").strip()
        if g:
            parts.append(g)
    return " ".join(parts)


EN_ES = {
    "and": "y",
    "the": "el",
    "<object marker>": "a",
    "seven": "siete",
    "three": "tres",
    "male": "macho",
    "female": "hembra",
    "stream": "arroyo",
    "to": "a",
    "upon": "sobre",
    "from": "de",
    "two": "dos",
    "five": "cinco",
    "eight": "ocho",
    "six": "seis",
    "<relative>": "que",
    "be light": "alumbrar",
    "earth": "tierra",
    "heavens": "cielos",
    "might": "fuerza",
    "duration": "duración",
    "this": "este",
    "walk": "vamos",
    "open field": "campo",
    "four": "cuatro",
    "be": "ser",
    "god(s)": "'Elohim",
    "pure": "puro",
    "YHWH": "YHWH",
    "creeping animals": "lo que repta",
    "together with": "con",
    "Egypt": "Egipto",
    "great": "grande",
    "Euphrates": "Éufrates",
    "sea": "mar",
    "at the back": "detrás",
    "coast, island": "isla",
    "field": "campo",
}


def load_plus_glosses():
    mapeo = json.load(
        (ROOT / "extras" / "texto samaritano" / "mapeo_genesis" / "genesis_texto_samaritano.json").open(encoding="utf-8")
    )
    by_verse = {}
    for ch in map(str, range(1, 11)):
        for vs, v in (mapeo.get("chapters") or {}).get(ch, {}).items():
            items = []
            for w in v.get("words") or []:
                if w.get("type") != "plus":
                    continue
                items.append((cons(w.get("sp_cons") or w.get("text") or ""), w.get("gloss") or ""))
            if items:
                by_verse[(int(ch), int(vs))] = items
    return by_verse


def _sp_cons(text: str) -> str:
    return cons(re.sub(r"^[:.]+", "", text or ""))


def plus_es(ch, vs, heb, plus_map, lex):
    c = _sp_cons(heb)
    if not c:
        return ""
    if c in PREFIX_BY_CONS and len(c) == 1:
        mapped = None
        for pc, gloss in plus_map.get((ch, vs), []):
            if pc == c:
                mapped = EN_ES.get(gloss)
                break
        return mapped or PREFIX_BY_CONS[c]
    hits = []
    for pc, gloss in plus_map.get((ch, vs), []):
        if not pc:
            continue
        if c == pc:
            hits.append((100, gloss))
        elif len(pc) >= 3 and (c.endswith(pc) or pc.endswith(c)):
            hits.append((len(pc), gloss))
    if hits:
        hits.sort(reverse=True)
        es = EN_ES.get(hits[0][1])
        if es:
            return es
    for key in (c, c[1:] if len(c) > 2 else ""):
        if key and key in lex:
            return lex[key]
    return ""


def apply_plus_es(target, words, ch, vs, plus_map, lex):
    bits = []
    for w in words:
        bit = (w.get("_pfx_es") or "").strip() or plus_es(ch, vs, w["text"], plus_map, lex)
        if bit:
            bits.append(bit)
    if bits:
        prev = (target.get("esSp") or "").strip()
        target["esSp"] = (prev + " " + " ".join(bits)).strip()


GR_FUNC = {
    "καὶ", "και", "δέ", "δε", "γάρ", "γαρ", "εἰς", "εις", "ἐν", "εν",
    "ἐκ", "εκ", "ἐξ", "εξ", "πρός", "προς", "ἀπό", "απο", "διά", "δια",
    "μετά", "μετα", "κατά", "κατα", "περί", "περι", "σύν", "συν",
    "ὑπέρ", "υπερ", "ὑπό", "υπο", "ὡς", "ως", "ὅτι", "οτι",
    "τό", "το", "τά", "τα", "τοῦ", "του", "τῆς", "της", "τῷ", "τω",
    "τῇ", "τη", "τόν", "τον", "τήν", "την", "τούς", "τους", "τάς", "τας",
    "τῶν", "των", "ὁ", "ο", "ἡ", "η", "οἱ", "οι", "αἱ", "αι", "οὐ", "ου",
    "μή", "μη", "τὸ",
}
HE_FUNC = {"ו", "ה", "ב", "ל", "מ", "כ", "ש", "את", "על", "אל", "מן"}


def _gr_parts(s: str) -> list[str]:
    raw = (s or "").lower().replace(";", " ").replace(",", " ")
    return [p for p in re.split(r"\s+", raw) if p]


def is_gr_func_cell(tok: dict) -> bool:
    parts = _gr_parts(tok.get("gr") or "")
    if not parts:
        return True
    return all(re.sub(r"[·’ʼʹʾ']", "", p) in GR_FUNC for p in parts)


def is_he_func_word(w: dict) -> bool:
    if w.get("role") == "prefix":
        return True
    return _sp_cons(w.get("text") or "") in HE_FUNC


def make_spadd(pluses, ch, vs, plus_map, lex) -> dict:
    tok = {
        "k": "spadd",
        "he": "",
        "morph": "ADD TS",
        "es": "—",
        "gr": "",
        "sp": " ".join(w["text"] for w in pluses),
        "spRed": True,
    }
    apply_plus_es(tok, pluses, ch, vs, plus_map, lex)
    return tok


# Copiado de motores/scripts/_restore_hebrew_oshb.py (role_of / PREFIX_HEADS).
# No se modifica ese motor: aquí solo se reutiliza el mismo criterio de morfemas.
PREFIX_HEADS = ("CONJ", "PREP", "ART", "PRT", "INTERR", "INTJ")
# Copiado de motores/scripts/populate_es_glosses.py PREFIX_BY_CONS + Td→el.
PREFIX_BY_CONS = {
    "ו": "y",
    "ב": "en",
    "ל": "a",
    "מ": "de",
    "כ": "como",
    "ש": "que",
    "ה": "el",
}


def morph_head(morph: str) -> str:
    return (morph or "").split(".")[0].split("+")[0].upper()


def is_prefix_morph(morph: str) -> bool:
    return morph_head(morph) in PREFIX_HEADS


def split_sp_like_motor(text: str, stems: set, pfx_by_cons: dict) -> list[dict]:
    """Parte el artículo proclítico como el motor (ART + stem).

    Misma autoridad que prefix_forms: si la forma entera ya es un stem
    (הלך, היה) no se toca; השדה no es stem y שדה sí → ה + שדה.
    PREP/CONJ del plus se dejan enteros para alinear con celdas LXX.
    """
    c = _sp_cons(text)
    if not c or c in stems:
        return [{"text": text, "role": "stem"}]
    parts = []
    rest = c
    while rest and rest not in stems:
        letter = rest[0]
        info = pfx_by_cons.get(letter)
        if not info or len(rest) < 3:
            break
        if letter != "ה" and morph_head(info.get("morph") or "") != "ART":
            break
        parts.append({
            "text": letter,
            "role": "prefix",
            "morph": info.get("morph") or "ART",
            "es": info.get("es") or PREFIX_BY_CONS.get(letter, ""),
        })
        rest = rest[1:]
    if not parts or rest not in stems:
        return [{"text": text, "role": "stem"}]
    parts.append({"text": rest, "role": "stem"})
    return parts


def expand_plus_words(pluses, stems, pfx_by_cons, adds):
    func_slots = sum(1 for a in adds if is_gr_func_cell(a))
    out = []
    for w in pluses:
        if func_slots <= 0:
            out.append(w)
            continue
        pieces = split_sp_like_motor(w.get("text") or "", stems, pfx_by_cons)
        if len(pieces) == 1:
            out.append(w)
            continue
        for p in pieces:
            nw = dict(w)
            nw["text"] = p["text"]
            nw["role"] = p["role"]
            if p.get("es") and p["role"] == "prefix":
                nw["_pfx_es"] = p["es"]
            out.append(nw)
        func_slots -= sum(1 for p in pieces if p["role"] == "prefix")
    return out


def _attach_one(target, words, ch, vs, plus_map, lex):
    target["sp"] = " ".join(x["text"] for x in words)
    target["spRed"] = True
    apply_plus_es(target, words, ch, vs, plus_map, lex)


def park_pluses_on_adds(adds, pluses, ch, vs, plus_map, lex, stems, pfx_by_cons) -> list:
    leftover = []
    if not pluses:
        return leftover
    if not adds:
        leftover.extend(pluses)
        return leftover
    pluses = expand_plus_words(pluses, stems, pfx_by_cons, adds)
    func_adds = [a for a in adds if is_gr_func_cell(a)]
    content_adds = [a for a in adds if not is_gr_func_cell(a)]
    func_sp = [w for w in pluses if is_he_func_word(w)]
    content_sp = [w for w in pluses if not is_he_func_word(w)]
    for i, w in enumerate(func_sp):
        if i < len(func_adds):
            _attach_one(func_adds[i], [w], ch, vs, plus_map, lex)
        else:
            leftover.append(w)
    for i, w in enumerate(content_sp):
        if i < len(content_adds):
            _attach_one(content_adds[i], [w], ch, vs, plus_map, lex)
        else:
            leftover.append(w)
    return leftover


def attach_sp(tokens, sp_verse, ch, vs, plus_map, lex, stems, pfx_by_cons):
    if not sp_verse:
        return tokens, ""
    words = [
        w for w in (sp_verse.get("words") or [])
        if w.get("text") and not str(w["text"]).startswith("—")
        and _sp_cons(w["text"])
    ]
    html = sp_verse.get("html") or ""
    plus_before = {}  # token index -> SP plus words that sit immediately before it
    i_sp = 0
    for i, t in enumerate(tokens):
        if t["k"] not in ("he", "pre"):
            continue
        c = t.get("cons") or cons(t.get("he") or "")
        if not c:
            continue
        skipped = []
        found = None
        for j in range(i_sp, min(i_sp + 10, len(words))):
            wc = _sp_cons(words[j]["text"])
            if not wc:
                continue
            if t["k"] == "pre":
                hit = wc == c
            else:
                hit = wc == c or (
                    min(len(wc), len(c)) >= 3
                    and (c.endswith(wc) or wc.endswith(c) or c in wc or wc in c)
                )
            if hit:
                found = j
                break
            if words[j].get("red"):
                skipped.append(words[j])
            else:
                break
        if found is None:
            continue
        if skipped:
            plus_before[i] = skipped
        t["sp"] = re.sub(r"^[:]+", "", words[found]["text"])
        t["spRed"] = bool(words[found].get("red"))
        i_sp = found + 1
    extra = [w for w in words[i_sp:] if w.get("red")]

    rebuilt = []
    i = 0
    while i < len(tokens):
        pluses = plus_before.get(i)
        if pluses:
            # ADDs immediately before this token
            k = len(rebuilt) - 1
            while k >= 0 and rebuilt[k]["k"] == "pre":
                k -= 1
            adds = []
            while k >= 0 and rebuilt[k]["k"] == "add":
                adds.append(rebuilt[k])
                k -= 1
            adds.reverse()
            if adds:
                leftover = park_pluses_on_adds(adds, pluses, ch, vs, plus_map, lex, stems, pfx_by_cons)
                for extra_w in leftover:
                    rebuilt.append(make_spadd([extra_w], ch, vs, plus_map, lex))
            else:
                rebuilt.append(make_spadd(pluses, ch, vs, plus_map, lex))
        rebuilt.append(tokens[i])
        i += 1
    unused_adds = [t for t in rebuilt if t["k"] == "add" and not t.get("sp")]
    if extra and unused_adds:
        extra = park_pluses_on_adds(unused_adds, extra, ch, vs, plus_map, lex, stems, pfx_by_cons)
    mt_cons = []
    for t in rebuilt:
        if t.get("k") == "he":
            c = t.get("cons") or cons(t.get("he") or "")
            if len(c) >= 3:
                mt_cons.append(c)

    def already_in_mt(w):
        wc = _sp_cons(w.get("text") or "")
        if len(wc) < 3:
            return False
        return any(c in wc or wc in c or wc.endswith(c) or c.endswith(wc) for c in mt_cons)

    extra = [w for w in extra if not already_in_mt(w)]
    if extra:
        rebuilt.append(make_spadd(extra, ch, vs, plus_map, lex))
    polish_plus_spanish(rebuilt)
    return rebuilt, html


ART_ES = {"el", "la", "los", "las"}
GR_A = {"εἰς", "εις", "πρός", "προς"}


def _gr_fold_tok(s: str) -> str:
    return re.sub(r"[·’ʼʹʾ']", "", (s or "").lower())


def contract_a_el(art: str, noun: str) -> str:
    noun = (noun or "").strip()
    art = (art or "").strip().lower()
    if noun.lower().startswith(("al ", "a la ", "a los ", "a las ")):
        return noun
    if art == "el":
        return f"al {noun}".strip()
    if art == "la":
        return f"a la {noun}".strip()
    if art == "los":
        return f"a los {noun}".strip()
    if art == "las":
        return f"a las {noun}".strip()
    return f"{art} {noun}".strip() if art else noun


def polish_plus_spanish(tokens: list) -> None:
    """εἰς + artículo ה + nombre → glosa «al campo», no «el» suelto."""
    for i, t in enumerate(tokens):
        spc = _sp_cons(t.get("sp") or "")
        es = (t.get("esSp") or "").strip().lower()
        if spc != "ה" and es not in ART_ES:
            continue
        if not t.get("spRed") and t.get("k") not in ("add", "spadd"):
            continue
        nxt = None
        for j in range(i + 1, min(i + 4, len(tokens))):
            tj = tokens[j]
            if tj.get("k") in ("add", "spadd") or tj.get("spRed"):
                if (tj.get("esSp") or "").strip():
                    nxt = tj
                    break
        if not nxt:
            continue
        grs = _gr_parts(t.get("gr") or "") + _gr_parts(nxt.get("gr") or "")
        folds = {_gr_fold_tok(g) for g in grs}
        if folds & GR_A:
            art = es if es in ART_ES else "el"
            nxt["esSp"] = contract_a_el(art, nxt.get("esSp") or "")
            t["esSp"] = ""


def esc_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def plus_runs(tokens: list) -> list[tuple[str | None, str]]:
    runs = []
    last_es = None
    buf = []

    def flush():
        if buf:
            runs.append((last_es, " ".join(buf)))
            buf.clear()

    for t in tokens:
        plus = t.get("k") in ("add", "spadd") and (t.get("esSp") or t.get("spRed"))
        if plus:
            es = (t.get("esSp") or "").strip()
            if es:
                buf.append(es)
        else:
            flush()
            es = (t.get("es") or "").strip()
            if es and es != "—":
                last_es = es
    flush()
    return runs


def personal_html(pers: str, tokens: list) -> str:
    runs = plus_runs(tokens)
    if not pers:
        bits = [p for _, p in runs if p]
        if not bits:
            return ""
        return " ".join(f'<span class="es-sp">{esc_html(p)}</span>' for p in bits)
    rest = pers
    parts = []
    for anchor, phrase in runs:
        if not phrase:
            continue
        span = f'<span class="es-sp">{esc_html(phrase)}</span>'
        idx = rest.lower().find(anchor.lower()) if anchor else -1
        if idx < 0:
            parts.append(span)
            parts.append(" ")
            continue
        end = idx + len(anchor)
        parts.append(esc_html(rest[:end]))
        rest = rest[end:]
        m = re.match(r"^([.!?]+)(\s*)", rest)
        if m:
            parts.append(esc_html(m.group(1)))
            rest = rest[len(m.group(0)):]
            parts.append(" ")
            parts.append(span)
            if rest[:1].isupper():
                parts.append(". ")
            else:
                parts.append(" ")
        else:
            parts.append(" ")
            parts.append(span)
            m2 = re.match(r"^\s*", rest)
            rest = rest[len(m2.group(0)):] if m2 else rest
            parts.append(" ")
    parts.append(esc_html(rest))
    return "".join(parts)


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    plus_map = load_plus_glosses()
    lex = {}
    stems = set()
    pfx_by_cons = {}
    book = json.load((ROOT / "data_master" / "genesis_final.json").open(encoding="utf-8"))
    personal = json.load((ROOT / "data_master" / "traduccion_personal_genesis.json").open(encoding="utf-8"))
    sp = json.load((OUT / "genesis_1_10_samaritano.json").open(encoding="utf-8"))
    chapters = {}
    pending = []
    for v in book["verses"]:
        ch, vs = v.get("chapter"), v.get("verse")
        if not ch or ch > 10:
            continue
        if v.get("is_lxx_add"):
            continue
        tokens = []
        for p in v.get("pairs") or []:
            tokens.extend(emit_pair(p))
        for t in tokens:
            c = t.get("cons") or cons(t.get("he") or "")
            es = (t.get("es") or "").strip()
            if c and es and es != "—":
                lex.setdefault(c, es)
            if t.get("k") == "he" and c:
                stems.add(c)
            if t.get("k") == "pre" and c and is_prefix_morph(t.get("morph") or ""):
                prev = pfx_by_cons.get(c)
                info = {
                    "morph": t.get("morph") or "",
                    "es": es if es != "—" else PREFIX_BY_CONS.get(c, ""),
                }
                if prev is None or morph_head(info["morph"]) == "ART":
                    pfx_by_cons[c] = info
        pending.append((ch, vs, tokens, v))
    for letter, gloss in PREFIX_BY_CONS.items():
        pfx_by_cons.setdefault(letter, {
            "morph": "ART" if letter == "ה" else "PREP" if letter != "ו" else "CONJ",
            "es": gloss,
        })
    for ch, vs, tokens, v in pending:
        sp_v = (sp.get("chapters") or {}).get(str(ch), {}).get(str(vs))
        tokens, sp_html = attach_sp(tokens, sp_v, ch, vs, plus_map, lex, stems, pfx_by_cons)
        pers = ""
        if len(personal) >= ch and len(personal[ch - 1]) >= vs:
            pers = (personal[ch - 1][vs - 1] or "").strip()
        chapters.setdefault(str(ch), {})[str(vs)] = {
            "tokens": tokens,
            "lxx": lxx_line(v.get("pairs") or []),
            "personal": pers,
            "personalHtml": personal_html(pers, tokens),
            "spHtml": sp_html,
            "nAdd": sum(1 for t in tokens if t["k"] == "add"),
        }
    data = {"book": "Génesis", "chapters": chapters}
    outp = OUT / "genesis_1_10_c4.json"
    outp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    v48 = chapters["4"]["8"]
    print("verses", sum(len(x) for x in chapters.values()), "bytes", outp.stat().st_size)
    print("4:8 tokens", len(v48["tokens"]))
    for t in v48["tokens"]:
        print(t["k"], t.get("es"), "esSp=", t.get("esSp"), "SP=", t.get("sp"))
    print("personal", v48["personal"])
    print("personalHtml", v48.get("personalHtml"))
    v14 = chapters["1"]["14"]
    print("--- 1:14 ---")
    for t in v14["tokens"]:
        if t["k"] in ("add", "spadd") or t.get("spRed"):
            print(t["k"], "esSp=", t.get("esSp"), "SP=", t.get("sp"), t.get("gr"))



if __name__ == "__main__":
    main()
