"""
Extract the Samaritan Pentateuch from DT-UCPH/sp Text-Fabric corpus
and convert from Hebrew script to genuine Samaritan script (Unicode U+0800-U+083F).
Output: samaritan_pentateuch.json
"""

import json
import sys
import os

# Hebrew consonant -> Samaritan Unicode mapping
HEBREW_TO_SAMARITAN = {
    '\u05D0': '\u0800',  # א -> ࠀ ALAF
    '\u05D1': '\u0801',  # ב -> ࠁ BIT
    '\u05D2': '\u0802',  # ג -> ࠂ GAMAN
    '\u05D3': '\u0803',  # ד -> ࠃ DALAT
    '\u05D4': '\u0804',  # ה -> ࠄ IY
    '\u05D5': '\u0805',  # ו -> ࠅ BAA
    '\u05D6': '\u0806',  # ז -> ࠆ ZEN
    '\u05D7': '\u0807',  # ח -> ࠇ IT
    '\u05D8': '\u0808',  # ט -> ࠈ TIT
    '\u05D9': '\u0809',  # י -> ࠉ YUT
    '\u05DA': '\u080A',  # ך -> ࠊ KAAF (final)
    '\u05DB': '\u080A',  # כ -> ࠊ KAAF
    '\u05DC': '\u080B',  # ל -> ࠋ LABAT
    '\u05DD': '\u080C',  # ם -> ࠌ MIM (final)
    '\u05DE': '\u080C',  # מ -> ࠌ MIM
    '\u05DF': '\u080D',  # ן -> ࠍ NUN (final)
    '\u05E0': '\u080D',  # נ -> ࠍ NUN
    '\u05E1': '\u080E',  # ס -> ࠎ SINGAAT
    '\u05E2': '\u080F',  # ע -> ࠏ IN
    '\u05E3': '\u0810',  # ף -> ࠐ FI (final)
    '\u05E4': '\u0810',  # פ -> ࠐ FI
    '\u05E5': '\u0811',  # ץ -> ࠑ TSAADIY (final)
    '\u05E6': '\u0811',  # צ -> ࠑ TSAADIY
    '\u05E7': '\u0812',  # ק -> ࠒ QUF
    '\u05E8': '\u0813',  # ר -> ࠓ RISH
    '\u05E9': '\u0814',  # ש -> ࠔ SHAN
    '\u05EA': '\u0815',  # ת -> ࠕ TAAF
    # Precomposed Hebrew Presentation Forms
    '\uFB2A': '\u0814',  # שׁ SHIN+SHIN DOT -> ࠔ SHAN
    '\uFB2B': '\u0814',  # שׂ SHIN+SIN DOT -> ࠔ SHAN
    '\uFB2C': '\u0814',  # שּׁ SHIN+DAGESH+SHIN DOT -> ࠔ
    '\uFB2D': '\u0814',  # שּׂ SHIN+DAGESH+SIN DOT -> ࠔ
    '\uFB2E': '\u0800',  # אַ ALEF+PATAH -> ࠀ
    '\uFB2F': '\u0800',  # אָ ALEF+QAMATS -> ࠀ
    '\uFB30': '\u0800',  # אּ ALEF+MAPIQ -> ࠀ
    '\uFB31': '\u0801',  # בּ BET+DAGESH -> ࠁ
    '\uFB32': '\u0802',  # גּ GIMEL+DAGESH -> ࠂ
    '\uFB33': '\u0803',  # דּ DALET+DAGESH -> ࠃ
    '\uFB34': '\u0804',  # הּ HE+MAPIQ -> ࠄ
    '\uFB35': '\u0805',  # וּ VAV+DAGESH -> ࠅ
    '\uFB36': '\u0806',  # זּ ZAYIN+DAGESH -> ࠆ
    '\uFB38': '\u0808',  # טּ TET+DAGESH -> ࠈ
    '\uFB39': '\u0809',  # יּ YOD+DAGESH -> ࠉ
    '\uFB3A': '\u080A',  # ךּ FINAL KAF+DAGESH -> ࠊ
    '\uFB3B': '\u080A',  # כּ KAF+DAGESH -> ࠊ
    '\uFB3C': '\u080B',  # לּ LAMED+DAGESH -> ࠋ
    '\uFB3E': '\u080C',  # מּ MEM+DAGESH -> ࠌ
    '\uFB40': '\u080D',  # נּ NUN+DAGESH -> ࠍ
    '\uFB41': '\u080E',  # סּ SAMEKH+DAGESH -> ࠎ
    '\uFB43': '\u0810',  # ףּ FINAL PE+DAGESH -> ࠐ
    '\uFB44': '\u0810',  # פּ PE+DAGESH -> ࠐ
    '\uFB46': '\u0811',  # צּ TSADI+DAGESH -> ࠑ
    '\uFB47': '\u0812',  # קּ QOF+DAGESH -> ࠒ
    '\uFB48': '\u0813',  # רּ RESH+DAGESH -> ࠓ
    '\uFB49': '\u0814',  # שּ SHIN+DAGESH -> ࠔ
    '\uFB4A': '\u0815',  # תּ TAV+DAGESH -> ࠕ
    '\uFB1D': '\u0809',  # יִ YOD+HIRIQ -> ࠉ
    '\uFB4B': '\u0805',  # וֹ VAV+HOLAM -> ࠅ
}

def hebrew_to_samaritan(text: str) -> str:
    result = []
    for ch in text:
        cp = ord(ch)
        if ch in HEBREW_TO_SAMARITAN:
            result.append(HEBREW_TO_SAMARITAN[ch])
        elif 0x0591 <= cp <= 0x05C7:
            pass  # skip Hebrew diacritics/cantillation
        elif ch in (' ', '\t', '\n', '-'):
            result.append(ch)
        elif cp < 0x0590 or cp > 0x05FF:
            result.append(ch)
    return ''.join(result)


def main():
    try:
        from tf.app import use
    except ImportError:
        print("Installing text-fabric...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "text-fabric"])
        from tf.app import use

    print("Loading Samaritan Pentateuch data from DT-UCPH/sp...")
    A = use('dt-ucph/sp', silent='deep')
    api = A.api
    F = api.F
    T = api.T
    L = api.L

    book_names_sam = {
        "Genesis": "ࠁࠓࠀࠔࠉࠕ",
        "Exodus": "ࠔࠌࠅࠕ",
        "Leviticus": "ࠅࠉࠒࠓࠀ",
        "Numbers": "ࠅࠉࠃࠁࠓ",
        "Deuteronomy": "ࠃࠁࠓࠉࠌ",
    }

    pentateuch = {}

    for book_node in F.otype.s('book'):
        book_name = F.book.v(book_node)
        book_name_sam = book_names_sam.get(book_name, book_name)
        print(f"  Processing {book_name}...")

        book_data = {
            "book_english": book_name,
            "book_samaritan": book_name_sam,
            "chapters": {}
        }

        for chapter_node in L.d(book_node, otype='chapter'):
            ch_num = str(F.chapter.v(chapter_node))
            chapter_data = {}

            for verse_node in L.d(chapter_node, otype='verse'):
                v_num = str(F.verse.v(verse_node))

                words_hebrew = []
                words_samaritan = []

                for word_node in L.d(verse_node, otype='word'):
                    w_heb = F.g_cons_utf8.v(word_node) or ''
                    trailer = F.trailer.v(word_node) or ''

                    w_sam = hebrew_to_samaritan(w_heb)
                    words_hebrew.append(w_heb)
                    words_samaritan.append(w_sam)

                verse_text_sam = ' '.join(words_samaritan)
                verse_text_heb = ' '.join(words_hebrew)

                chapter_data[v_num] = {
                    "samaritan": verse_text_sam,
                    "hebrew_source": verse_text_heb,
                    "words": words_samaritan
                }

            book_data["chapters"][ch_num] = chapter_data

        pentateuch[book_name] = book_data

    output_path = os.path.join(os.path.dirname(__file__), "samaritan_pentateuch.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(pentateuch, f, ensure_ascii=False, indent=2)

    total_words = sum(
        len(v["words"])
        for b in pentateuch.values()
        for c in b["chapters"].values()
        for v in c.values()
    )
    total_verses = sum(
        len(c)
        for b in pentateuch.values()
        for c in b["chapters"].values()
    )
    total_chapters = sum(len(b["chapters"]) for b in pentateuch.values())

    print(f"\nDone!")
    print(f"  Books: {len(pentateuch)}")
    print(f"  Chapters: {total_chapters}")
    print(f"  Verses: {total_verses}")
    print(f"  Words: {total_words}")
    print(f"  Output: {output_path}")

    # Show sample
    gen1 = pentateuch.get("Genesis", {}).get("chapters", {}).get("1", {})
    if "1" in gen1:
        print(f"\n  Sample - Genesis 1:1 (Samaritan script):")
        print(f"    {gen1['1']['samaritan']}")
        print(f"  Sample - Genesis 1:1 (Hebrew source):")
        print(f"    {gen1['1']['hebrew_source']}")


if __name__ == '__main__':
    main()
