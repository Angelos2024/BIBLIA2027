# -*- coding: utf-8 -*-
"""Extract SP Hebrew column (Tal–Florentin PDF), preserving red vs black."""
import json
import re
import sys
from pathlib import Path

import fitz

sys.stdout.reconfigure(encoding="utf-8")

PDF = Path(
    r"C:\Users\Angelos\Desktop\BIBLIA2027\septuaginta"
    r"\The Samaritan Pentateuch An English Translation with a Parallel Annotated Hebrew Text.pdf"
)
OUT_DIR = Path(r"C:\Users\Angelos\Desktop\BIBLIA2027\septuaginta\samaritan_tal_florentin")
RED = 16711680  # #FF0000
HEB_COL_X = 270
BODY_Y_MIN = 70
BODY_SIZE_MIN = 12.5
VERSE_NUM_SIZE = (8.0, 10.2)
HEADER_SIZE_MAX = 10.5

HEB_LETTERS = "אבגדהוזחטיכלמנסעפצקרשת"
GERESH = "\u05f3"
CHAPTER_VAL = {c: i + 1 for i, c in enumerate(HEB_LETTERS)}


def heb_num(s: str) -> int | None:
    """Hebrew letter-numerals used as chapter labels (א … נ / יא …)."""
    s = s.strip().replace(GERESH, "").replace("׳", "")
    if not s or len(s) > 3 or any(ch not in CHAPTER_VAL for ch in s):
        return None
    total = 0
    for ch in s:
        total += CHAPTER_VAL[ch]
    if total < 1 or total > 50:
        return None
    return total


def is_verse_num(text: str, size: float) -> int | None:
    if not (VERSE_NUM_SIZE[0] <= size <= VERSE_NUM_SIZE[1]):
        return None
    t = re.sub(r"[\s\u00a0\u2000-\u200f\u2028-\u202f\u205f\u3000]+", "", text)
    if re.fullmatch(r"\d{1,3}", t):
        return int(t)
    return None


def split_words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


def extract_page_tokens(page, apparatus_y: float | None):
    d = page.get_text("dict")
    lines = []  # (y, [(x, size, font, color, text, bold)])
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            row = []
            ys = []
            for s in l["spans"]:
                font = s.get("font") or ""
                if "Hebrew" not in font:
                    continue
                x0, y0, x1, y1 = s["bbox"]
                if x0 < HEB_COL_X:
                    continue
                size = s.get("size") or 0
                if y0 < BODY_Y_MIN:
                    continue
                if apparatus_y is not None and y0 >= apparatus_y - 4:
                    continue
                # running header leftover
                if size <= HEADER_SIZE_MAX and y0 < 60:
                    continue
                # body text or verse numbers
                is_num = is_verse_num(s["text"], size) is not None
                if size < BODY_SIZE_MIN and not is_num:
                    continue
                row.append(
                    {
                        "x": x0,
                        "y": y0,
                        "size": size,
                        "font": font,
                        "color": s.get("color") or 0,
                        "text": s["text"],
                        "bold": "Bold" in font,
                    }
                )
                ys.append(y0)
            if row:
                lines.append((sum(ys) / len(ys), row))
    lines.sort(key=lambda t: t[0])
    tokens = []
    for y, row in lines:
        row.sort(key=lambda t: t["x"])
        # RTL: reverse visual order
        for item in reversed(row):
            vn = is_verse_num(item["text"], item["size"])
            if vn is not None:
                tokens.append({"kind": "verse", "n": vn, "y": y})
                continue
            txt = item["text"].strip()
            if item["bold"] and heb_num(txt) is not None and item["size"] >= 12:
                tokens.append({"kind": "chapter", "n": heb_num(txt), "raw": txt, "y": y})
                continue
            if item["bold"] and item["size"] >= 16:
                tokens.append({"kind": "title", "text": txt, "y": y})
                continue
            words = split_words(item["text"])
            if not words:
                continue
            # Span text is stored LTR (visual); reverse for Hebrew reading order.
            words.reverse()
            red = item["color"] == RED
            for w in words:
                tokens.append({"kind": "word", "text": w, "red": red, "y": y})
    return tokens


def find_apparatus_y(page) -> float | None:
    d = page.get_text("dict")
    ys = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                font = s.get("font") or ""
                t = s["text"].strip()
                size = s.get("size") or 0
                y0 = s["bbox"][1]
                if font.startswith("CharisSIL-Bold") and size < 11 and re.match(r"^\d+\.\d+", t):
                    ys.append(y0)
    return min(ys) if ys else None


def build(doc, start_page_1based: int, stop_chapter: int):
    chapters = {}
    cur_ch = None
    cur_vs = None
    words = []
    skipped_before = True

    def flush_verse():
        nonlocal words, cur_ch, cur_vs
        if cur_ch is None or cur_vs is None:
            words = []
            return
        if not words:
            return
        ch = chapters.setdefault(cur_ch, {})
        word_list = [{"text": w["text"], "red": w["red"]} for w in words]
        verse = {"text": " ".join(w["text"] for w in words), "words": word_list}
        verse["html"] = verse_html(verse)
        ch[cur_vs] = verse
        words = []

    for pno in range(start_page_1based - 1, doc.page_count):
        page = doc[pno]
        app_y = find_apparatus_y(page)
        # if no apparatus, still cut small notes near bottom? body never below ~520 without apparatus sometimes
        tokens = extract_page_tokens(page, app_y)
        page_1 = pno + 1
        for tok in tokens:
            if tok["kind"] == "title":
                continue
            if tok["kind"] == "chapter":
                n = tok["n"]
                if n >= stop_chapter:
                    flush_verse()
                    return chapters, page_1
                if skipped_before and n != 1:
                    continue
                flush_verse()
                cur_ch = n
                cur_vs = None
                skipped_before = False
                continue
            if skipped_before:
                continue
            if tok["kind"] == "verse":
                flush_verse()
                cur_vs = tok["n"]
                continue
            if tok["kind"] == "word":
                if cur_ch is None:
                    continue
                if cur_vs is None:
                    # text before first verse number on a chapter - attach later? rare
                    continue
                words.append(tok)
        # continue pages
    flush_verse()
    return chapters, None


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def verse_html(verse: dict) -> str:
    """Merge consecutive same-color words into one span (cleaner red runs)."""
    parts = []
    buf = []
    red = None

    def flush():
        if not buf:
            return
        chunk = esc(" ".join(buf))
        if red:
            parts.append(f'<span class="red">{chunk}</span>')
        else:
            parts.append(chunk)
        buf.clear()

    for w in verse["words"]:
        if red is None:
            red = bool(w["red"])
        elif bool(w["red"]) != red:
            flush()
            red = bool(w["red"])
        buf.append(w["text"])
    flush()
    return " ".join(parts)


def write_html(data: dict, path: Path):
    nav = " · ".join(
        f'<a href="#c{ch}">Gn {ch}</a>' for ch in data["chapters"]
    )
    rows = []
    for ch, verses in data["chapters"].items():
        rows.append(f'<h2 id="c{ch}">בראשית {ch}</h2>')
        for vn, v in verses.items():
            note = v.get("note")
            extra = f'\n  <span class="note"> {esc(note)}</span>' if note else ""
            rows.append(
                f'<p class="v" dir="rtl"><span class="vn">{ch}:{vn}</span> {verse_html(v)}{extra}</p>'
            )
    body = "\n".join(rows)
    html = f"""<!DOCTYPE html>
<html lang="he">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Pentateuco samaritano — Génesis 1–10 (ejemplo)</title>
<style>
:root {{ --red:#c1121f; --ink:#1a120c; --muted:#5c4a3a; }}
body {{
  font-family: "SBL Hebrew","Frank Ruehl CLM","David","Times New Roman",serif;
  max-width: 860px; margin: 24px auto 64px; padding: 0 18px;
  color: var(--ink); background: #fbf7f0;
}}
h1, .ui {{ font-family: "Segoe UI", Arial, sans-serif; }}
h1 {{ font-size: 1.35rem; margin-bottom: 8px; }}
.note, .nav {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 0.92rem; color: var(--muted); }}
.nav {{ position: sticky; top: 0; background: #fbf7f0ee; padding: 8px 0 10px; border-bottom: 1px solid #e6d7c4; z-index: 2; }}
.nav a {{ color: #6b2a12; text-decoration: none; margin: 0 2px; }}
.legend {{ margin: 14px 0 22px; padding: 10px 14px; background: #fff; border: 1px solid #e0d0bc; border-radius: 8px; }}
.swatch {{ display: inline-block; width: 11px; height: 11px; border-radius: 2px; margin: 0 4px 0 10px; vertical-align: -1px; }}
.swatch.k {{ background: #1a120c; }}
.swatch.r {{ background: var(--red); }}
h2 {{ color: #6b2a12; border-bottom: 1px solid #e0d0bc; padding: 18px 0 6px; }}
.v {{ font-size: 1.55rem; line-height: 1.85; text-align: right; margin: 0.35em 0; }}
.vn {{ font-family: "Segoe UI", Arial, sans-serif; font-size: 0.72rem; color: #8c5a20;
      vertical-align: super; margin-left: 8px; }}
.red {{ color: var(--red); font-weight: 700; }}
.v .note {{ display: block; font-size: 0.85rem; text-align: right; margin-top: 4px; }}
</style>
</head>
<body>
<h1 class="ui">Texto hebreo samaritano — Génesis 1–10</h1>
<p class="nav">{nav}</p>
<p class="note">Edición: Moshe Florentin &amp; Abraham Tal. Solo la columna hebrea del PDF.
El <span class="red">rojo</span> es la marca de diferencia SP/TM; el negro es el resto del samaritano.</p>
<p class="legend note"><span class="swatch k"></span> texto común
<span class="swatch r"></span> <span class="red">variante / plus (rojo del PDF)</span></p>
{body}
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(PDF)
    chapters, stop_at = build(doc, 104, stop_chapter=11)
    expected = {1: 31, 2: 25, 3: 24, 4: 26, 5: 32, 6: 22, 7: 24, 8: 22, 9: 29, 10: 32}
    # Esta edición no numera Gn 6:20; el plus equivalente va en rojo dentro de 6:19.
    if 6 in chapters and 20 not in chapters[6] and 19 in chapters[6]:
        chapters[6][20] = {
            "text": "",
            "words": [],
            "html": "",
            "note": "Sin número de verso en la edición; el texto paralelo al TM 6:20 está marcado en rojo al final de 6:19.",
        }
    stats = {}
    for ch in range(1, 11):
        vs = chapters.get(ch, {})
        nums = sorted(int(k) for k in vs)
        nred = sum(1 for v in vs.values() for w in v["words"] if w["red"])
        stats[ch] = {
            "verses": len(vs),
            "verse_numbers": nums,
            "missing": [i for i in range(1, expected[ch] + 1) if i not in vs],
            "extra": [i for i in nums if i > expected[ch] or i < 1],
            "red_words": nred,
            "words": sum(len(v["words"]) for v in vs.values()),
        }
        print(f"Gen {ch}: {stats[ch]['verses']} vs (expect {expected[ch]}) missing={stats[ch]['missing']} extra={stats[ch]['extra']} red_words={nred}")
        if 1 in vs:
            print("   1:1 ", vs[1]["text"][:80])
            reds = " ".join(w["text"] for w in vs[1]["words"] if w["red"])
            if reds:
                print("   red ", reds)

    # stringify chapter/verse keys
    ch_out = {}
    for ch, verses in sorted(chapters.items(), key=lambda x: int(x[0])):
        ch_out[str(ch)] = {}
        for vn, v in sorted(verses.items(), key=lambda x: int(x[0])):
            ch_out[str(ch)][str(vn)] = v

    data = {
        "source": {
            "pdf": PDF.name,
            "authors": "Moshe Florentin & Abraham Tal",
            "title": "The Samaritan Pentateuch: An English Translation with a Parallel Annotated Hebrew Text",
            "scope": "Genesis 1–10, Hebrew Samaritan column only (not English, not apparatus)",
            "red": "#CC0000 / PDF color #FF0000: SP vs MT marking in the edition",
        },
        "legend": {
            "red": True,
            "black": False,
        },
        "stats": stats,
        "stopped_before_page": stop_at,
        "chapters": ch_out,
    }
    json_path = OUT_DIR / "genesis_1_10_samaritano.json"
    html_path = OUT_DIR / "genesis_1_10_samaritano.html"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_html(data, html_path)
    print("wrote", json_path)
    print("wrote", html_path)


if __name__ == "__main__":
    main()
