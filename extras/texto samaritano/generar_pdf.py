"""
Genera un PDF con la Lectura Samaritana completa de la Toráh.
Texto hebreo RTL, portada discreta, introducción académica.
"""
import json, sys, os, unicodedata
from fpdf import FPDF
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r'C:\Users\pik_y\Documents\TRADUCCION\texto samaritano'
ORDER = ['genesis', 'exodus', 'leviticus', 'numbers', 'deuteronomy']
NAMES_HE = {
    'genesis': 'בראשית', 'exodus': 'שמות', 'leviticus': 'ויקרא',
    'numbers': 'במדבר', 'deuteronomy': 'דברים'
}
NAMES_ES = {
    'genesis': 'Génesis', 'exodus': 'Éxodo', 'leviticus': 'Levítico',
    'numbers': 'Números', 'deuteronomy': 'Deuteronomio'
}

FRANK = r'C:\Windows\Fonts\frank.ttf'
ARIAL = r'C:\Windows\Fonts\arial.ttf'
ARIAL_BOLD = r'C:\Windows\Fonts\arialbd.ttf'
ARIAL_ITALIC = r'C:\Windows\Fonts\ariali.ttf'

HEB_SIZE = 15
HEB_LINE = 9


def _is_mark(ch):
    return unicodedata.category(ch).startswith('M')

def rtl(text):
    """Reverse Hebrew grapheme clusters for correct visual order in LTR PDF."""
    words = text.split(' ')
    out = []
    for word in words:
        clusters = []
        cur = []
        for ch in word:
            if _is_mark(ch):
                cur.append(ch)
            else:
                if cur:
                    clusters.append(''.join(cur))
                cur = [ch]
        if cur:
            clusters.append(''.join(cur))
        clusters.reverse()
        out.append(''.join(clusters))
    out.reverse()
    return ' '.join(out)


class ToraPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self.add_font('Hebrew', '', FRANK)
        self.add_font('Body', '', ARIAL)
        self.add_font('Body', 'B', ARIAL_BOLD)
        self.add_font('Body', 'I', ARIAL_ITALIC)
        self.set_auto_page_break(True, margin=20)
        self.current_book = ''

    def header(self):
        if self.page_no() <= 2:
            return
        self.set_font('Body', 'I', 9)
        self.set_text_color(120, 100, 80)
        self.cell(0, 8, f'Lectura Samaritana de la Toráh  —  {self.current_book}', align='L')
        self.cell(0, 8, f'{self.page_no()}', align='R', new_x='LMARGIN', new_y='NEXT')
        self.set_draw_color(200, 185, 160)
        self.line(10, 16, 200, 16)
        self.ln(3)

    def footer(self):
        if self.page_no() <= 2:
            self.set_y(-15)
            self.set_font('Body', 'I', 8)
            self.set_text_color(150)
            self.cell(0, 10, f'{self.page_no()}', align='C')

    def hebrew_verse(self, vnum, text):
        vnum_w = 12
        text_w = self.w - self.l_margin - self.r_margin - vnum_w
        x0 = self.get_x()
        y0 = self.get_y()

        self.set_font('Hebrew', '', HEB_SIZE)
        self.set_text_color(40, 30, 20)
        rtext = rtl(text)

        nb = self.multi_cell(text_w, HEB_LINE, rtext, align='R',
                             new_x='RIGHT', new_y='TOP', dry_run=True, output='LINES')
        h = len(nb) * HEB_LINE

        self.set_xy(x0, y0)
        self.multi_cell(text_w, HEB_LINE, rtext, align='R',
                        new_x='RIGHT', new_y='TOP')

        self.set_font('Body', 'B', 9)
        self.set_text_color(140, 110, 70)
        self.set_xy(x0 + text_w, y0)
        self.cell(vnum_w, HEB_LINE, f'  {vnum}', align='L')

        self.set_xy(x0, y0 + h)
        self.ln(0.5)
        if self.get_y() > 270:
            self.add_page()


pdf = ToraPDF()

# ── PORTADA ──
pdf.add_page()
pdf.ln(45)
pdf.set_font('Hebrew', '', 38)
pdf.set_text_color(60, 35, 20)
pdf.cell(0, 18, rtl('\u05ea\u05d5\u05e8\u05ea \u05d4\u05e9\u05de\u05e8\u05d5\u05e0\u05d9\u05dd'),
         align='C', new_x='LMARGIN', new_y='NEXT')
pdf.ln(10)
pdf.set_font('Body', 'B', 26)
pdf.cell(0, 14, 'Lectura Samaritana de la Toráh', align='C',
         new_x='LMARGIN', new_y='NEXT')
pdf.ln(5)
pdf.set_font('Body', '', 14)
pdf.set_text_color(100, 75, 50)
pdf.cell(0, 10, 'Pentateuco Samaritano vocalizado en hebreo cuadrado',
         align='C', new_x='LMARGIN', new_y='NEXT')
pdf.ln(18)
pdf.set_draw_color(180, 150, 110)
pdf.line(60, pdf.get_y(), 150, pdf.get_y())

pdf.set_y(-35)
pdf.set_font('Body', '', 10)
pdf.set_text_color(120, 100, 80)
pdf.cell(0, 5, 'Ing. Miguel Ángel Roan Rodriguez', align='L',
         new_x='LMARGIN', new_y='NEXT')
pdf.set_font('Body', 'I', 9)
pdf.set_text_color(150, 130, 110)
pdf.cell(0, 5, datetime.now().strftime('%B %Y'), align='L',
         new_x='LMARGIN', new_y='NEXT')

# ── INTRODUCCION ──
pdf.add_page()
pdf.set_text_color(60, 35, 20)
pdf.set_font('Body', 'B', 20)
pdf.cell(0, 12, 'Introducción', new_x='LMARGIN', new_y='NEXT')
pdf.ln(4)
pdf.set_draw_color(180, 150, 110)
pdf.line(10, pdf.get_y(), 200, pdf.get_y())
pdf.ln(6)
pdf.set_font('Body', '', 11)
pdf.set_text_color(40, 30, 20)

intro = [
    "El presente documento contiene la vocalización completa del Pentateuco Samaritano (SP) "
    "en hebreo cuadrado con niqqud (signos vocálicos). Constituye, hasta donde sabemos, "
    "el primer corpus digital que representa la pronunciación samaritana tradicional de la "
    "Toráh en un formato procesable por computadora.",
    "La comunidad samaritana, que hoy cuenta con apenas 800 miembros divididos entre Holon "
    "y el Monte Gerizim, preserva una tradición oral de lectura de la Toráh que difiere "
    "sustancialmente de la pronunciación masorética (tiberiana) conocida por la mayoría de "
    "los estudiosos del hebreo bíblico. Hasta ahora, la única referencia escrita para esta "
    "pronunciación eran los textos impresos de Benyamim Tsedaka y la gramática monumental "
    "de Ze'ev Ben-Hayyim, ambos inaccesibles al procesamiento digital.",
    "El desafío técnico central radicaba en que no existe ningún corpus digital con la "
    "vocalización samaritana. Los intentos de aplicar OCR a los textos impresos de Tsedaka "
    "fracasaron sistemáticamente (Tesseract, ABBYY y modelos especializados), debido a que "
    "los diacríticos vocálicos samaritanos son diminutos y no están soportados por ningún "
    "motor de reconocimiento óptico de caracteres existente.",
    "La solución implementada consiste en un motor de reglas fonológicas (Motor Samaritano v6) "
    "que toma como entrada la vocalización masorética del corpus ETCBC/BHSA y la transforma "
    "mediante las reglas fonológicas documentadas por Ben-Hayyim para la tradición oral samaritana. "
    "El texto consonantal de referencia proviene del corpus digital dt-ucph/sp del Pentateuco "
    "Samaritano.",
    "El proceso de producción involucró los siguientes pasos:",
]
for p in intro:
    pdf.multi_cell(0, 5.5, p, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

steps = [
    "Alineamiento del texto consonantal SP con el texto masorético mediante el algoritmo "
    "de Needleman-Wunsch, tolerando variaciones en matres lectionis.",
    "Transferencia de la vocalización masorética al esqueleto consonantal samaritano para "
    "las palabras con emparejamiento exacto o difuso (94.6%).",
    "Aplicación de 13 reglas fonológicas samaritanas: conversión del cholam a qubuts/qamats, "
    "eliminación de sheva, transformación de hataf a vocal plena, ajuste del plural masculino "
    "(-im a -em), entre otras.",
    "Resolución léxica de 4,890 palabras exclusivas del SP mediante armonización con formas "
    "vocalizadas encontradas en otros contextos del corpus.",
    "Curación manual de 63 formas únicas del SP sin paralelo masorético, incluyendo el "
    "emblemático Monte Gerizim.",
    "Correcciones editoriales de post-procesamiento: erradicación global del sin-dot "
    "(la tradición samaritana no distingue shin de sin), aplicación de dagesh protector en "
    "Bet/Kaf/Pe, normalización de participios activos Qal con qamats, ajuste del plural "
    "femenino -ot a -at, y corrección de la partícula negativa a /la/.",
]
for j, s in enumerate(steps):
    pdf.set_font('Body', 'B', 11)
    pdf.cell(8, 5.5, f'{j+1}.')
    pdf.set_font('Body', '', 11)
    pdf.multi_cell(0, 5.5, s, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(2)

pdf.ln(2)
final = [
    "El resultado es un corpus de 116,208 palabras con cobertura de vocalización del 100% "
    "y calidad fonológica del 100% (medida como ausencia de residuos masoréticos detectables "
    "por las reglas del motor). El emparejamiento MT-SP alcanzó el 94.6% (89.4% exacto + "
    "5.2% difuso).",
    "Es importante señalar que la calidad reportada representa consistencia interna con las "
    "reglas fonológicas implementadas, no una validación contra el \"gold standard\" de la "
    "pronunciación samaritana oral. Tal validación requeriría acceso digital a los textos "
    "impresos de Tsedaka o a grabaciones fonéticas sistematizadas de la lectura litúrgica "
    "samaritana, recursos que al momento de esta publicación no están disponibles en formato "
    "procesable.",
    "Este corpus se ofrece como herramienta de investigación para lingüistas, biblistas y "
    "estudiosos de las tradiciones textuales del Pentateuco. Los datos están disponibles "
    "también en formato JSON para facilitar su procesamiento computacional."
]
for p in final:
    pdf.multi_cell(0, 5.5, p, new_x='LMARGIN', new_y='NEXT')
    pdf.ln(3)

# ── TEXTO COMPLETO ──
for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    name_es = NAMES_ES[b]
    name_he = NAMES_HE[b]
    pdf.current_book = name_es

    pdf.add_page()
    pdf.set_font('Body', 'B', 24)
    pdf.set_text_color(60, 35, 20)
    pdf.cell(0, 14, name_es, align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.set_font('Hebrew', '', 28)
    pdf.cell(0, 16, rtl(name_he), align='C', new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)
    pdf.set_draw_color(180, 150, 110)
    pdf.line(50, pdf.get_y(), 160, pdf.get_y())
    pdf.ln(8)

    chapters = sorted(data['chapters'].keys(), key=int)
    print(f'{name_es}: {len(chapters)} capítulos...')

    for ch in chapters:
        chap = data['chapters'][ch]
        if pdf.get_y() > 240:
            pdf.add_page()
        pdf.set_font('Body', 'B', 14)
        pdf.set_text_color(100, 60, 30)
        pdf.cell(0, 9, f'Capítulo {ch}', align='R', new_x='LMARGIN', new_y='NEXT')
        pdf.ln(2)
        pdf.set_text_color(40, 30, 20)
        for vs in sorted(chap.keys(), key=int):
            sam = chap[vs]['sam_reading']
            pdf.hebrew_verse(vs, sam)

out_path = os.path.join(BASE, 'Lectura_Samaritana_Torah_MiguelAngelRoanRodriguez.pdf')
pdf.output(out_path)
sz = os.path.getsize(out_path) / (1024 * 1024)
print(f'\nPDF generado: {out_path}')
print(f'Tamaño: {sz:.2f} MB')
print(f'Páginas: {pdf.page_no()}')
