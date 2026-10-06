#!/usr/bin/env python3
"""Exporta un capítulo BHSA (ETCBC / Parabible) a JSON + SQLite.

Fuente: text-fabric corpus `bhsa` — misma base que parabible/data-module-bhsa.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from unicodedata import normalize

ROOT = Path(__file__).resolve().parent.parent

BOOK_INDEX = {
    "Genesis": 1,
    "Exodus": 2,
    "Leviticus": 3,
    "Numbers": 4,
    "Deuteronomy": 5,
}


def passage_to_rid(book: str, chapter: int, verse: int) -> int:
    if book not in BOOK_INDEX:
        raise ValueError(f"Libro no soportado en piloto: {book}")
    return BOOK_INDEX[book] * 1_000_000 + chapter * 1_000 + verse


def normify(word: str) -> str:
    return normalize("NFC", word or "")


def convert_part_of_speech(part: str) -> str:
    if part == "subs":
        return "noun"
    if part == "adjv":
        return "adj"
    return part


def convert_gender(gn: str) -> str | None:
    if gn == "m":
        return "masc"
    if gn == "f":
        return "fem"
    if gn in ("NA", "unknown", ""):
        return None
    return gn


def convert_na(value: str) -> str | None:
    return None if value in ("na", "NA", "", "unknown") else value


def maybe_is_definite(F, L, n) -> str | None:
    definiteness = F.det.v(L.u(n, otype="phrase_atom")[0])
    return {"det": "Y", "und": "N", "NA": None}.get(definiteness)


def word_features(F, L, T, n: int) -> dict:
    """Morfología al estilo Parabible (panel derecho de parabible.com)."""
    out: dict = {"wid": int(n)}

    def put(key: str, val) -> None:
        if val is None or val == "" or val == "NA" or val == "unknown":
            return
        out[key] = val

    put("text", normify(F.g_word_utf8.v(n)))
    put("trailer", normify(F.trailer_utf8.v(n)))
    put("qere", normify(F.qere_utf8.v(n)))
    put("consonantal_root", normify(F.lex_utf8.v(n)))
    put("lexeme", normify(F.voc_lex_utf8.v(L.u(n, otype="lex")[0])))
    put("realized_lexeme", normify(F.g_lex_utf8.v(n)))
    put("gloss", F.gloss.v(L.u(n, otype="lex")[0]))
    put("part_of_speech", convert_part_of_speech(F.sp.v(n)))

    ps = F.ps.v(n)
    put("person", ps[1] if ps in ("p1", "p2", "p3") else None)
    put("number", F.nu.v(n))
    put("gender", convert_gender(F.gn.v(n)))
    put("tense", F.vt.v(n))
    put("stem", convert_na(F.vs.v(n).lower() if F.vs.v(n) else ""))
    put("state", convert_na(F.st.v(n).lower() if F.st.v(n) else ""))
    put("is_definite", maybe_is_definite(F, L, n))

    g_prs = ""
    if hasattr(F, "g_prs_utf8"):
        g_prs = normify(F.g_prs_utf8.v(n))
    put("g_prs_utf8", g_prs)
    if g_prs:
        put("has_pronominal_suffix", "Y")
    put("pron_suffix_number", F.prs_nu.v(n))
    put("pron_suffix_gender", convert_gender(F.prs_gn.v(n)))
    prs_ps = F.prs_ps.v(n)
    put(
        "pron_suffix_person",
        prs_ps[1] if prs_ps in ("p1", "p2", "p3") else None,
    )

    put("phrase_function", F.function.v(L.u(n, otype="phrase")[0]))
    put("phrase_node_id", int(L.u(n, otype="phrase")[0]))
    put("clause_node_id", int(L.u(n, otype="clause")[0]))
    put("sentence_node_id", int(L.u(n, otype="sentence")[0]))

    # Paralelo LXX (PARALLEL LEXEME en UI Parabible) — si existe en corpus
    for attr in ("lxxlexeme", "lxx_lexeme", "lxx"):
        if hasattr(F, attr):
            try:
                val = getattr(F, attr).v(n)
                if val and val not in ("NA", "unknown"):
                    put("lxx_lexeme", normify(str(val)))
                    break
            except Exception:
                pass

    section = T.sectionFromNode(n)
    ref_str = f"{section[0]} {section[1]} {section[2]}"
    put("reference", ref_str)
    put("book", section[0])
    put("chapter", int(section[1]))
    put("verse", int(section[2]))
    out["rid"] = passage_to_rid(section[0], int(section[1]), int(section[2]))
    return out


def iter_chapter_words(A, F, book: str, chapter: int):
    """Yield (verse_num, word_node) in canonical order."""
    from collections import defaultdict

    query = f"""
book book={book}
  chapter chapter={chapter}
    verse
      word
"""
    hits = A.search(query)
    by_verse: dict[int, list[int]] = defaultdict(list)
    for tup in hits:
        verse_node, word_node = tup[-2], tup[-1]
        by_verse[int(F.verse.v(verse_node))].append(int(word_node))

    for verse in sorted(by_verse):
        yield verse, by_verse[verse]


def export_chapter(book: str, chapter: int, out_dir: Path) -> dict:
    from tf.app import use

    out_dir.mkdir(parents=True, exist_ok=True)
    print("Cargando corpus ETCBC/bhsa — primera vez puede descargar datos…")
    A = use("ETCBC/bhsa", silent=True)
    F = A.api.F
    L = A.api.L
    T = A.api.T

    verses_out: list[dict] = []
    words_out: list[dict] = []

    for verse, word_nodes in iter_chapter_words(A, F, book, chapter):
        ref = f"{book} {chapter} {verse}"
        verse_words: list[dict] = []
        for n in word_nodes:
            feat = word_features(F, L, T, n)
            words_out.append(feat)
            verse_words.append(
                {
                    "wid": feat["wid"],
                    "word": feat.get("text", ""),
                    "trailer": feat.get("trailer", ""),
                }
            )

        verses_out.append(
            {
                "reference": ref,
                "rid": passage_to_rid(book, chapter, verse),
                "verse": verse,
                "word_count": len(verse_words),
                "words": verse_words,
            }
        )

    if not verses_out:
        raise RuntimeError(f"Sin versos exportados para {book} {chapter}")

    meta = {
        "source": "ETCBC BHSA via text-fabric",
        "parabible_module": "BHSA",
        "license": "CC BY-NC 4.0",
        "book": book,
        "chapter": chapter,
        "verse_count": len(verses_out),
        "word_count": len(words_out),
        "url": "https://etcbc.github.io/bhsa/",
    }

    json_words = out_dir / "bhsa_words.json"
    json_verses = out_dir / "bhsa_verses.json"
    json_meta = out_dir / "meta.json"
    sqlite_path = out_dir / "bhsa_chapter.sqlite"
    if sqlite_path.exists():
        sqlite_path.unlink()

    json_words.write_text(
        json.dumps(words_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_verses.write_text(
        json.dumps(verses_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    json_meta.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE word_features (
            wid INTEGER PRIMARY KEY,
            rid INTEGER,
            reference TEXT,
            text TEXT,
            trailer TEXT,
            lexeme TEXT,
            consonantal_root TEXT,
            gloss TEXT,
            part_of_speech TEXT,
            person TEXT,
            number TEXT,
            gender TEXT,
            tense TEXT,
            stem TEXT,
            state TEXT,
            is_definite TEXT,
            has_pronominal_suffix TEXT,
            g_prs_utf8 TEXT,
            lxx_lexeme TEXT,
            features_json TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE verse_text (
            rid INTEGER PRIMARY KEY,
            reference TEXT,
            verse INTEGER,
            text_json TEXT
        )
        """
    )

    for w in words_out:
        cur.execute(
            """
            INSERT INTO word_features (
                wid, rid, reference, text, trailer, lexeme, consonantal_root,
                gloss, part_of_speech, person, number, gender, tense, stem,
                state, is_definite, has_pronominal_suffix, g_prs_utf8,
                lxx_lexeme, features_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                w.get("wid"),
                w.get("rid"),
                w.get("reference"),
                w.get("text"),
                w.get("trailer"),
                w.get("lexeme"),
                w.get("consonantal_root"),
                w.get("gloss"),
                w.get("part_of_speech"),
                w.get("person"),
                w.get("number"),
                w.get("gender"),
                w.get("tense"),
                w.get("stem"),
                w.get("state"),
                w.get("is_definite"),
                w.get("has_pronominal_suffix"),
                w.get("g_prs_utf8"),
                w.get("lxx_lexeme"),
                json.dumps(w, ensure_ascii=False),
            ),
        )

    for v in verses_out:
        cur.execute(
            "INSERT INTO verse_text (rid, reference, verse, text_json) VALUES (?,?,?,?)",
            (v["rid"], v["reference"], v["verse"], json.dumps(v["words"], ensure_ascii=False)),
        )

    conn.commit()
    conn.close()

    print(f"  versos: {len(verses_out)}, palabras: {len(words_out)}")
    print(f"  {json_words}")
    print(f"  {sqlite_path}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="Export BHSA chapter (Parabible source)")
    ap.add_argument("--book", default="Genesis")
    ap.add_argument("--chapter", type=int, default=10)
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "genesis" / "10",
        help="Directorio de salida",
    )
    args = ap.parse_args()
    meta = export_chapter(args.book, args.chapter, args.out)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
