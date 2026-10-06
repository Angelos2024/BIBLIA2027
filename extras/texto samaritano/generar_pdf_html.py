"""
Genera PDF de la Lectura Samaritana via HTML + Brave headless.
Misma calidad de renderizado que el visor HTML.
"""
import json, os, subprocess, sys
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

BRAVE = r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe'

print("Construyendo HTML para impresión...")

html_parts = ['''<!DOCTYPE html>
<html lang="he" dir="ltr">
<head>
<meta charset="utf-8">
<title>Lectura Samaritana de la Toráh</title>
<style>
@page {
  size: A4;
  margin: 20mm 18mm 22mm 18mm;
}
body {
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 11pt;
  color: #2a1e14;
  line-height: 1.5;
}

/* Title page */
.title-page {
  page-break-after: always;
  text-align: center;
  padding-top: 120px;
  position: relative;
  min-height: 700px;
}
.title-he {
  font-family: "SBL Hebrew", "Frank Ruehl CLM", "FrankRuehl", "David", serif;
  font-size: 40pt;
  color: #3c2314;
  direction: rtl;
  margin-bottom: 20px;
}
.title-es {
  font-size: 24pt;
  font-weight: bold;
  color: #3c2314;
  margin-bottom: 10px;
}
.subtitle {
  font-size: 13pt;
  color: #644b32;
  margin-bottom: 40px;
}
.title-line {
  width: 120px;
  border: none;
  border-top: 1.5px solid #b4966e;
  margin: 0 auto;
}
.author-block {
  position: absolute;
  bottom: 40px;
  left: 0;
  text-align: left;
  font-size: 10pt;
  color: #786450;
}
.author-block .date {
  font-style: italic;
  font-size: 9pt;
  color: #968270;
}

/* Introduction */
.intro-page {
  page-break-after: always;
}
.intro-page h1 {
  font-size: 20pt;
  color: #3c2314;
  margin-bottom: 4px;
}
.intro-page hr {
  border: none;
  border-top: 1.5px solid #b4966e;
  margin-bottom: 16px;
}
.intro-page p {
  text-align: justify;
  margin-bottom: 8px;
}
.intro-page ol {
  padding-left: 20px;
}
.intro-page ol li {
  margin-bottom: 6px;
  text-align: justify;
}

/* Book pages */
.book-title {
  page-break-before: always;
  text-align: center;
  padding-top: 30px;
  margin-bottom: 10px;
}
.book-title .es {
  font-size: 22pt;
  font-weight: bold;
  color: #3c2314;
}
.book-title .he {
  font-family: "SBL Hebrew", "Frank Ruehl CLM", "FrankRuehl", "David", serif;
  font-size: 28pt;
  color: #3c2314;
  direction: rtl;
}
.book-title hr {
  width: 140px;
  border: none;
  border-top: 1.5px solid #b4966e;
  margin: 12px auto 20px;
}

.chapter-head {
  font-size: 13pt;
  font-weight: bold;
  color: #643c1e;
  text-align: right;
  margin-top: 18px;
  margin-bottom: 6px;
}

.verse {
  direction: rtl;
  text-align: right;
  font-family: "SBL Hebrew", "Frank Ruehl CLM", "FrankRuehl", "David", "Noto Serif Hebrew", serif;
  font-size: 20pt;
  line-height: 2.2;
  margin-bottom: 4px;
  color: #1a1410;
  letter-spacing: 0.02em;
}
.verse .vn {
  font-family: "Segoe UI", Arial, sans-serif;
  font-size: 10pt;
  font-weight: bold;
  color: #8c6e46;
  vertical-align: super;
  margin-left: 8px;
  direction: ltr;
  unicode-bidi: embed;
}

@media print {
  .no-break { page-break-inside: avoid; }
}
</style>
</head>
<body>
''']

# ── PORTADA ──
html_parts.append(f'''
<div class="title-page">
  <div class="title-he">תורת השמרונים</div>
  <div class="title-es">Lectura Samaritana de la Toráh</div>
  <div class="subtitle">Pentateuco Samaritano vocalizado en hebreo cuadrado</div>
  <hr class="title-line">
  <div class="author-block">
    Ing. Miguel Ángel Roan Rodriguez<br>
    <span class="date">{datetime.now().strftime("%B %Y")}</span>
  </div>
</div>
''')

# ── INTRODUCCION ──
html_parts.append('''
<div class="intro-page">
<h1>Introducción</h1>
<hr>

<p>El presente documento contiene la vocalización completa del Pentateuco Samaritano (SP)
en hebreo cuadrado con niqqud (signos vocálicos). Constituye, hasta donde sabemos,
el primer corpus digital que representa la pronunciación samaritana tradicional de la
Toráh en un formato procesable por computadora.</p>

<p>La comunidad samaritana, que hoy cuenta con apenas 800 miembros divididos entre Holon
y el Monte Gerizim, preserva una tradición oral de lectura de la Toráh que difiere
sustancialmente de la pronunciación masorética (tiberiana) conocida por la mayoría de
los estudiosos del hebreo bíblico. Hasta ahora, la única referencia escrita para esta
pronunciación eran los textos impresos de Benyamim Tsedaka y la gramática monumental
de Ze'ev Ben-Hayyim, ambos inaccesibles al procesamiento digital.</p>

<p>El desafío técnico central radicaba en que no existe ningún corpus digital con la
vocalización samaritana. Los intentos de aplicar OCR a los textos impresos de Tsedaka
fracasaron sistemáticamente (Tesseract, ABBYY y modelos especializados), debido a que
los diacríticos vocálicos samaritanos son diminutos y no están soportados por ningún
motor de reconocimiento óptico de caracteres existente.</p>

<p>La solución implementada consiste en un motor de reglas fonológicas (Motor Samaritano v6)
que toma como entrada la vocalización masorética del corpus ETCBC/BHSA y la transforma
mediante las reglas fonológicas documentadas por Ben-Hayyim para la tradición oral samaritana.
El texto consonantal de referencia proviene del corpus digital dt-ucph/sp del Pentateuco
Samaritano.</p>

<p>El proceso de producción involucró los siguientes pasos:</p>

<ol>
<li>Alineamiento del texto consonantal SP con el texto masorético mediante el algoritmo
de Needleman-Wunsch, tolerando variaciones en matres lectionis.</li>
<li>Transferencia de la vocalización masorética al esqueleto consonantal samaritano para
las palabras con emparejamiento exacto o difuso (94.6%).</li>
<li>Aplicación de 13 reglas fonológicas samaritanas: conversión del cholam a qubuts/qamats,
eliminación de sheva, transformación de hataf a vocal plena, ajuste del plural masculino
(-im a -em), entre otras.</li>
<li>Resolución léxica de 4,890 palabras exclusivas del SP mediante armonización con formas
vocalizadas encontradas en otros contextos del corpus.</li>
<li>Curación manual de 63 formas únicas del SP sin paralelo masorético, incluyendo el
emblemático Monte Gerizim.</li>
<li>Correcciones editoriales de post-procesamiento: erradicación global del sin-dot
(la tradición samaritana no distingue shin de sin), aplicación de dagesh protector en
Bet/Kaf/Pe, normalización de participios activos Qal con qamats, ajuste del plural
femenino -ot a -at, y corrección de la partícula negativa a /la/.</li>
</ol>

<p>El resultado es un corpus de 116,208 palabras con cobertura de vocalización del 100%
y calidad fonológica del 100% (medida como ausencia de residuos masoréticos detectables
por las reglas del motor). El emparejamiento MT-SP alcanzó el 94.6% (89.4% exacto +
5.2% difuso).</p>

<p>Es importante señalar que la calidad reportada representa consistencia interna con las
reglas fonológicas implementadas, no una validación contra el "gold standard" de la
pronunciación samaritana oral. Tal validación requeriría acceso digital a los textos
impresos de Tsedaka o a grabaciones fonéticas sistematizadas de la lectura litúrgica
samaritana, recursos que al momento de esta publicación no están disponibles en formato
procesable.</p>

<p>Este corpus se ofrece como herramienta de investigación para lingüistas, biblistas y
estudiosos de las tradiciones textuales del Pentateuco. Los datos están disponibles
también en formato JSON para facilitar su procesamiento computacional.</p>
</div>
''')

# ── TEXTO POR LIBRO ──
for b in ORDER:
    path = os.path.join(BASE, f'{b}_lectura_samaritana.json')
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    name_es = NAMES_ES[b]
    name_he = NAMES_HE[b]
    print(f'{name_es}: {len(data["chapters"])} capítulos...')

    html_parts.append(f'''
<div class="book-title">
  <div class="es">{name_es}</div>
  <div class="he">{name_he}</div>
  <hr>
</div>
''')

    for ch in sorted(data['chapters'].keys(), key=int):
        chap = data['chapters'][ch]
        html_parts.append(f'<div class="chapter-head">Capítulo {ch}</div>\n')

        for vs in sorted(chap.keys(), key=int):
            sam = chap[vs]['sam_reading']
            safe = sam.replace('&', '&amp;').replace('<', '&lt;')
            html_parts.append(
                f'<div class="verse">{safe} <span class="vn">{vs}</span></div>\n'
            )

html_parts.append('</body></html>')

html_path = os.path.join(BASE, '_print_torah.html')
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(''.join(html_parts))

html_size = os.path.getsize(html_path) / (1024 * 1024)
print(f'HTML generado: {html_path} ({html_size:.2f} MB)')

# ── CONVERTIR A PDF CON BRAVE HEADLESS ──
pdf_path = os.path.join(BASE, 'Lectura_Samaritana_Torah_MiguelAngelRoanRodriguez.pdf')
print('Convirtiendo a PDF con Brave headless...')

cmd = [
    BRAVE,
    '--headless',
    '--disable-gpu',
    '--no-sandbox',
    '--run-all-compositor-stages-before-draw',
    '--print-to-pdf=' + pdf_path,
    '--print-to-pdf-no-header',
    html_path
]

result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
if result.returncode != 0:
    print(f'STDERR: {result.stderr}')
    print(f'STDOUT: {result.stdout}')
    sys.exit(1)

pdf_size = os.path.getsize(pdf_path) / (1024 * 1024)
print(f'\nPDF generado: {pdf_path}')
print(f'Tamaño: {pdf_size:.2f} MB')
print('¡Listo!')
