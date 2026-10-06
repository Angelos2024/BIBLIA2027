"""_restaurar_en.py — Restaura glosas [EN:...] a español correcto.

Escanea tokens cuyo campo `es` contiene placeholders en inglés como `[EN:work]`,
`[EN:to]`, etc. y los reemplaza con la traducción española correcta mediante
tres capas de resolución (en orden de prioridad):

  1. EDICIONES DEL USUARIO (glosas_personales.json):
     - Regla de contexto: posición exacta (book/chapter/verse/pairIdx/hwIdx) -> aplica.
     - Regla global: misma forma + Strong -> aplica.
  2. CORPUS: si el mismo Strong tiene glosa ES no-[EN:] en otros versículos del
     corpus, usa la más frecuente.
  3. TABLA EN→ES: diccionario de fallback para EN comunes (preposiciones, verbos,
     sustantivos frecuentes, nombres propios).

Lo que no se puede resolver queda reportado en CSV pendiente para revisión manual.

SOLO modifica el campo `es` del he_word. Nunca toca hebreo, he_morph, griego/LXX,
prefijos ni sufijos. Salta posiciones con es_source='glosa_personal'. Escritura
atómica + respaldo. Reporte CSV.

Uso:
  python scripts/_restaurar_en.py --book <slug> [--apply]
  (sin --apply = dry-run)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from glosas_personales_utils import atomic_write_json, load_registry  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP_DIR = DATA / "_fluidez_backup"

# ── Tabla EN→ES de fallback ───────────────────────────────────────────────────
EN_ES_TABLE: dict[str, str] = {
    # Preposiciones / partículas
    "to": "a", "for": "para", "from": "de", "of": "de", "on": "sobre",
    "in": "en", "with": "con", "as": "como", "like": "como", "when": "cuando",
    "not": "no", "apart": "aparte", "the": "", "(for": "para", "(to)": "a",
    "(in)": "en", "go": "ir", "[will]": "",
    "[belongs] to": "pertenece a", "[belong] to": "pertenece a",
    "[belonged] to": "perteneció a",
    # Sustantivos comunes
    "work": "obra", "children": "hijos", "sons": "hijos", "kind": "especie",
    "nostrils": "narices", "desire": "deseo", "breadth": "anchura",
    "height": "altura", "side": "costado", "ribs": "costillas",
    "offering": "ofrenda", "bruise": "herida", "wound": "herida",
    "generations": "generaciones", "youth(s)": "juventud",
    "cold": "frío", "summer": "verano", "winter": "invierno",
    "language": "lengua", "languages": "lenguas", "lands": "tierras",
    "four": "cuatro", "northward": "al norte", "southward": "al sur",
    "westward": "al oeste", "own": "propia", "his own": "suya",
    "their own": "suya", "its own": "suya", "their hill": "su monte",
    "reward": "recompensa",
    "journeyings": "jornadas", "wage[s]": "salario", "fire": "fuego",
    "sheep": "oveja", "rams": "carneros", "horns": "cuernos",
    "end": "extremo", "border": "límite", "property": "posesión",
    "acquisition": "posesión", "weight": "peso", "ark": "arca",
    "fear": "temor", "the fear": "el temor", "lives": "vidas",
    "here": "aquí", "thing": "cosa", "report": "informe",
    "sheaf": "gavilla", "cord": "cordón", "staff": "vara",
    "friend": "amigo", "quiver": "aljaba", "account": "razón",
    "righteousness": "justicia", "body": "cuerpo", "company": "asamblea",
    "assembly": "asamblea", "inheritance": "herencia", "swords": "espadas",
    "council": "consejo", "pleasure": "voluntad", "wrath": "furor",
    "clothing": "vestidura", "deliverance": "salvación", "kingdom": "reino",
    "laws": "leyes", "villages": "aldeas", "encampments": "campamentos",
    "blossom": "flor", "clusters": "racimos", "sins": "pecados",
    "loins": "lomos", "weeping": "llanto", "his weeping": "su llanto",
    "male goats": "machos cabríos", "bulls": "toros", "birthright": "primogenitura",
    "posterity": "posteridad", "progeny": "descendencia",
    "entreat": "supliquen", "spotted": "manchados",
    "the innocence": "la inocencia", "my heart": "mi corazón",
    "your heart": "tu corazón", "heart": "corazón", "the heart": "el corazón",
    "sand": "arena", "the sand": "la arena", "the inner": "lo interior",
    "the front of": "frente a", "the tendon": "el tendón", "tendon": "tendón",
    "a wise [person]": "un sabio", "signet-ring": "anillo de sello",
    "father-in-law": "suegro", "my roof": "mi techo",
    "[was] around": "alrededor", "[were] around": "alrededores",
    "[was] in": "en", "[is] like": "como", "[is] the Sea": "el mar",
    "escaped remnant": "remanente", "the ford": "el vado",
    "than the portions": "que las porciones",
    "your inward": "tus entrañas", "your sojournings": "tus peregrinaciones",
    "I have served": "he servido", "three days ago": "hace tres días",
    "you longed": "anhelabas", "gods": "dioses",
    "of his head": "de su cabecera", "his kingdom": "su reino",
    "sound": "sonido", "belly": "vientre", "your face": "tu rostro",
    "my": "mi",
    # Verbos
    "he": "", "I": "", "they": "", "you": "", "she conceived": "concibió",
    "he looked": "miró", "he walked about": "caminó",
    "they walked": "caminaron", "they covered": "cubrieron",
    "they went": "fueron", "meet": "encuentro", "take": "tomar",
    "sun": "puesta del sol", "hunt": "caza", "have": "has engañado",
    "let": "alimenta", "he divided": "dividió", "he stayed the night": "pasó la noche",
    "stay the night": "pasar la noche", "they stayed the night": "pasaron la noche",
    "he remained": "quedó", "he wrestled": "luchó", "wrestled": "luchar",
    "you have struggled": "has luchado", "he asked": "preguntó",
    "it has been delivered": "ha sido librada", "it rose": "salió",
    "they met": "encontraron", "a gift": "un regalo",
    "I will go to the right": "iré a la derecha",
    "I will go to the left": "iré a la izquierda",
    # Nombres propios (se mantienen)
    "Tubal-Cain": "Tubal-Caín", "Rehoboth-Ir": "Rehobot-Ir",
    "Ashteroth": "Astarot", "Hazezon": "Hazezón", "Melchizedek": "Melquisedec",
    "Peniel": "Peniel", "Lahai": "Lajai", "Arba": "Arba",
    "of Ammon": "de Amón", "Jebusite[s]": "jebuseos", "Arodi": "Arodi",
    "Migdal": "Migdal", "Zaphenath-Paneah": "Zafnat-panea",
    "[hay]": "hay",
    # ── Expansión corpus-wide (top pendientes) ────────────────────────────
    # Sustantivos frecuentes
    "king": "rey", "feet": "pies", "enemies": "enemigos", "daughters": "hijas",
    "the midst": "el medio", "ears": "oídos", "gates": "puertas",
    "law": "ley", "tongue": "lengua", "ear": "oído", "strength": "fuerza",
    "deeds": "obras", "tents": "tiendas", "houses": "casas", "mouth": "boca",
    "livestock": "ganado", "lips": "labios", "voice": "voz", "throne": "trono",
    "judgments": "juicios", "places": "lugares", "abominations": "abominaciones",
    "iniquities": "iniquidades", "bones": "huesos", "place": "lugar",
    "prayer": "oración", "appearance": "apariencia", "foot": "pie",
    "the heavens": "los cielos", "men": "hombres", "faithfulness": "fidelidad",
    "idols": "ídolos", "priests": "sacerdotes", "statutes": "estatutos",
    "salvation": "salvación", "ancestors": "antepasados",
    "their ancestors": "sus antepasados", "my lord": "mi señor",
    "of hosts": "de los ejércitos", "it": "",
    # Preposiciones / adverbios / partículas
    "by": "por", "among": "entre", "eastward": "al este", "more": "más",
    "(the)": "", "will": "",
    # Verbos comunes
    "make": "hacer", "do": "hacer",
    # Nombres propios frecuentes
    "David": "David", "Selah": "Selah", "Lord": "Señor", "lord": "señor",
    "Jerusalem": "Jerusalén", "Moses": "Moisés", "God": "Dios",
    "Solomon": "Salomón", "Daniel": "Daniel", "Ramoth": "Ramot",
    "Israel": "Israel", "Judah": "Judá", "Egypt": "Egipto",
    "Babylon": "Babilonia", "Zion": "Sion", "Aaron": "Aarón",
    "Levi": "Leví", "Jacob": "Jacob", "Joseph": "José",
    "[those": "aquellos",
    # Cuerpo / naturaleza
    "head": "cabeza", "hand": "mano", "hands": "manos", "eye": "ojo",
    "eyes": "ojos", "blood": "sangre", "flesh": "carne", "seed": "semilla",
    "tree": "árbol", "trees": "árboles", "stone": "piedra", "stones": "piedras",
    "gold": "oro", "silver": "plata", "iron": "hierro", "brass": "bronce",
    "wood": "madera", "oil": "aceite", "wine": "vino", "bread": "pan",
    "fruit": "fruto", "field": "campo", "fields": "campos",
    "mountain": "monte", "mountains": "montes", "valley": "valle",
    "river": "río", "sea": "mar", "wilderness": "desierto",
    "city": "ciudad", "cities": "ciudades", "wall": "muro", "walls": "muros",
    "door": "puerta", "doors": "puertas",
    # Guerra / gobierno
    "sword": "espada", "battle": "batalla", "war": "guerra",
    "army": "ejército", "captain": "capitán", "servant": "siervo",
    "servants": "siervos", "master": "amo", "people": "pueblo",
    "nations": "naciones", "judge": "juez", "judges": "jueces",
    # Familia / sociedad
    "father": "padre", "mother": "madre", "brother": "hermano",
    "brothers": "hermanos", "sister": "hermana", "wife": "esposa",
    "husband": "esposo", "son": "hijo", "daughter": "hija",
    # Religión / culto
    "altar": "altar", "sacrifice": "sacrificio", "burnt offering": "holocausto",
    "temple": "templo", "tabernacle": "tabernáculo", "priest": "sacerdote",
    "prophet": "profeta", "prophets": "profetas",
    "commandments": "mandamientos", "commandment": "mandamiento",
    "covenant": "pacto", "mercy": "misericordia", "grace": "gracia",
    "glory": "gloria", "praise": "alabanza", "sin": "pecado",
    "transgression": "transgresión", "iniquity": "iniquidad",
    "wickedness": "maldad", "righteousness": "justicia",
    "truth": "verdad", "peace": "paz", "joy": "gozo",
    "anger": "ira", "wrath": "furor", "fury": "furia",
    # Tiempo
    "morning": "mañana", "evening": "tarde", "night": "noche",
    "day": "día", "days": "días", "year": "año", "years": "años",
    "month": "mes", "months": "meses", "time": "tiempo",
    "forever": "para siempre", "always": "siempre",
    # Otros sustantivos
    "name": "nombre", "names": "nombres", "word": "palabra", "words": "palabras",
    "way": "camino", "ways": "caminos", "path": "sendero",
    "power": "poder", "wisdom": "sabiduría", "knowledge": "conocimiento",
    "understanding": "entendimiento", "counsel": "consejo",
    "spirit": "espíritu", "soul": "alma", "life": "vida",
    "death": "muerte", "deep": "profundo",
    "rock": "roca", "dust": "polvo", "earth": "tierra",
    "heaven": "cielo", "heavens": "cielos", "cloud": "nube",
    "rain": "lluvia", "wind": "viento", "darkness": "tinieblas",
    "light": "luz",
    # Adjetivos
    "great": "grande", "small": "pequeño", "many": "muchos",
    "evil": "malo", "good": "bueno", "holy": "santo",
    "right": "diestra", "left": "izquierda", "new": "nuevo", "old": "viejo",
    "first": "primero", "last": "último", "high": "alto",
    # ── Expansión V3 (top pendientes corpus-wide) ────────────────────────
    "that": "", "which": "", "may": "", "she": "", "we": "",
    "any": "", "this": "", "now": "", "thus": "", "did": "",
    "under": "debajo", "around": "alrededor", "besides": "además",
    "than": "que", "within": "dentro", "because": "porque",
    "outside": "afuera", "south": "sur",
    "honor": "honor", "bed": "lecho", "wings": "alas",
    "valuation": "valuación", "sanctuary": "santuario",
    "interpretation": "interpretación", "offerings": "ofrendas",
    "the tribe": "la tribu", "Levites": "levitas",
    "their drink": "su libación", "might": "poder",
    "neck": "cuello", "falsehood": "falsedad",
    "a generation": "una generación", "save": "salva",
    "refuge": "refugio", "the sea": "el mar", "officials": "oficiales",
    "bosom": "seno", "testimonies": "testimonios", "altars": "altares",
    "help": "ayuda", "dream": "sueño", "the king": "el rey",
    "their military": "su ejército", "of Aaron": "de Aarón",
    "wonders": "maravillas", "fathers": "padres",
    "their grain": "su grano", "the middle": "el medio",
    "foes": "adversarios", "thousand(s)": "miles", "times": "veces",
    "horses": "caballos", "enemy": "enemigo", "sacrifices": "sacrificios",
    "splendor": "esplendor", "they said": "dijeron",
    "bars": "barras", "perpetuity": "perpetuidad", "branches": "ramas",
    "sides": "lados", "hope": "esperanza",
    "pillars": "columnas", "division": "división", "decrees": "decretos",
    "of David": "de David", "vineyards": "viñas", "horn": "cuerno",
    "the valley": "el valle", "uncleanness": "inmundicia",
    "the four": "los cuatro", "pieces": "pedazos", "give": "dar",
    "produce": "producir", "of reed[s]": "de caña",
    "[am] commanding": "mando", "be]": "",
    "(diy) that": "", "(diy) of": "de",
    "shaqeh": "copero", "[those": "aquellos",
    # Más sustantivos
    "spear": "lanza", "shield": "escudo", "chariot": "carro",
    "chariots": "carros", "horse": "caballo", "ox": "buey",
    "oxen": "bueyes", "donkey": "asno", "donkeys": "asnos",
    "camel": "camello", "camels": "camellos", "lamb": "cordero",
    "lambs": "corderos", "goat": "cabra", "goats": "cabras",
    "birds": "aves", "fish": "pez", "lion": "león",
    "bear": "oso", "serpent": "serpiente", "eagle": "águila",
    "dove": "paloma", "wolf": "lobo",
    "garden": "jardín", "tent": "tienda", "house": "casa",
    "roof": "techo", "floor": "piso", "window": "ventana",
    "tower": "torre", "gate": "puerta", "camp": "campamento",
    "wilderness": "desierto", "forest": "bosque", "plain": "llanura",
    "shore": "orilla", "island": "isla",
    "north": "norte", "east": "este", "west": "oeste",
    "cup": "copa", "vessel": "vasija", "vessels": "vasijas",
    "table": "mesa", "lamp": "lámpara", "lamps": "lámparas",
    "throne": "trono", "crown": "corona", "ring": "anillo",
    "chains": "cadenas", "robe": "manto", "garment": "vestido",
    "garments": "vestidos", "linen": "lino", "wool": "lana",
    "ivory": "marfil", "purple": "púrpura",
    # Más verbos
    "bring": "traer", "send": "enviar", "call": "llamar",
    "hear": "oír", "see": "ver", "know": "saber",
    "speak": "hablar", "say": "decir", "tell": "decir",
    "come": "venir", "return": "volver", "turn": "volver",
    "stand": "estar de pie", "sit": "sentarse", "walk": "caminar",
    "run": "correr", "fall": "caer", "rise": "levantarse",
    "fight": "pelear", "kill": "matar", "die": "morir",
    "live": "vivir", "eat": "comer", "drink": "beber",
    "sleep": "dormir", "weep": "llorar", "rejoice": "regocijarse",
    "praise": "alabar", "pray": "orar", "swear": "jurar",
    "judge": "juzgar", "rule": "gobernar", "reign": "reinar",
    "build": "edificar", "destroy": "destruir", "break": "romper",
    "burn": "quemar", "plant": "plantar", "sow": "sembrar",
    "reap": "cosechar", "gather": "reunir", "scatter": "esparcir",
    "open": "abrir", "shut": "cerrar", "fill": "llenar",
    "pour": "derramar", "wash": "lavar", "anoint": "ungir",
    "bless": "bendecir", "curse": "maldecir", "forgive": "perdonar",
    "redeem": "redimir", "deliver": "librar", "heal": "sanar",
    "teach": "enseñar", "learn": "aprender",
    "seek": "buscar", "find": "hallar", "hide": "esconder",
    "keep": "guardar", "watch": "velar", "wait": "esperar",
    "trust": "confiar", "believe": "creer", "obey": "obedecer",
    "serve": "servir", "worship": "adorar", "sing": "cantar",
    "play": "tocar", "write": "escribir", "read": "leer",
    "count": "contar", "measure": "medir", "weigh": "pesar",
    "buy": "comprar", "sell": "vender", "pay": "pagar",
    "steal": "robar", "lie": "mentir",
    # ── Expansión V4 (cola larga) ─────────────────────────────────────────
    "selves": "", "who": "", "before": "ante", "except": "excepto",
    "toil": "trabajo", "continually": "continuamente",
    "prostitution(s)": "prostitución", "rebuke": "reprensión",
    "his military": "su ejército", "service": "servicio",
    "the field": "el campo", "stronghold": "fortaleza",
    "horsemen": "jinetes", "poles": "varas", "sickness": "enfermedad",
    "[the] sea": "el mar", "fortresses": "fortalezas", "lover": "amante",
    "burning": "ardor", "thoughts": "pensamientos", "by day": "de día",
    "beauty": "hermosura", "vows": "votos", "of meeting": "de reunión",
    "Jordan": "Jordán", "affliction": "aflicción", "put": "poner",
    "sabbaths": "sábados", "things": "cosas", "Absalom": "Absalón",
    "image": "imagen", "humankind": "humanidad",
    "Nebuchadnezzar": "Nabucodonosor", "the fire": "el fuego",
    "Jews": "judíos", "dominion": "dominio", "the end": "el fin",
    "writing": "escritura", "fearing": "temiendo",
    "satraps": "sátrapas", "Gilead": "Galaad",
    # Cuerpo
    "shoulder": "hombro", "shoulders": "hombros", "face": "rostro",
    "faces": "rostros", "hair": "cabello", "skin": "piel",
    "back": "espalda", "breast": "pecho", "thigh": "muslo",
    "teeth": "dientes", "tooth": "diente", "finger": "dedo",
    "fingers": "dedos", "palm": "palma",
    # Naturaleza
    "waters": "aguas", "streams": "arroyos", "brook": "arroyo",
    "spring": "manantial", "springs": "manantiales", "well": "pozo",
    "wells": "pozos", "lake": "lago", "flood": "diluvio",
    "storm": "tormenta", "thunder": "trueno", "lightning": "relámpago",
    "star": "estrella", "stars": "estrellas", "moon": "luna",
    "flower": "flor", "flowers": "flores", "leaf": "hoja",
    "leaves": "hojas", "root": "raíz", "roots": "raíces",
    "vine": "vid", "vineyard": "viña", "harvest": "cosecha",
    "grain": "grano", "wheat": "trigo", "barley": "cebada",
    # Objetos / materiales
    "bow": "arco", "arrow": "flecha", "arrows": "flechas",
    "net": "red", "hook": "anzuelo", "yoke": "yugo",
    "plow": "arado", "sickle": "hoz", "hammer": "martillo",
    "nail": "clavo", "nails": "clavos", "rope": "cuerda",
    "ropes": "cuerdas", "basket": "canasta", "pot": "olla",
    "jar": "jarra", "pitcher": "cántaro",
    # Abstractos
    "fear": "temor", "love": "amor", "hate": "odio",
    "shame": "vergüenza", "pride": "orgullo", "humility": "humildad",
    "patience": "paciencia", "jealousy": "celos", "pity": "piedad",
    "compassion": "compasión", "vengeance": "venganza",
    "guilt": "culpa", "burden": "carga", "rest": "descanso",
    "trouble": "angustia", "sorrow": "dolor", "grief": "duelo",
    "abundance": "abundancia", "plenty": "abundancia",
    "famine": "hambruna", "poverty": "pobreza", "wealth": "riqueza",
    "profit": "ganancia", "wages": "salario",
    "plague": "plaga", "plagues": "plagas", "wound": "herida",
    "sign": "señal", "signs": "señales", "miracle": "milagro",
    "wonder": "maravilla", "mystery": "misterio",
    "promise": "promesa", "oath": "juramento", "vow": "voto",
    "blessing": "bendición", "blessings": "bendiciones",
    "judgment": "juicio", "decree": "decreto", "statute": "estatuto",
    "testimony": "testimonio", "witness": "testigo",
    "remembrance": "recuerdo", "memorial": "memorial",
    "portion": "porción", "portions": "porciones",
    # Más nombres propios
    "Ephraim": "Efraín", "Manasseh": "Manasés", "Benjamin": "Benjamín",
    "Reuben": "Rubén", "Simeon": "Simeón", "Issachar": "Isacar",
    "Zebulun": "Zabulón", "Dan": "Dan", "Naphtali": "Neftalí",
    "Gad": "Gad", "Asher": "Aser", "Samaria": "Samaria",
    "Moab": "Moab", "Edom": "Edom", "Philistine": "filisteo",
    "Philistines": "filisteos", "Assyria": "Asiria",
    "Persia": "Persia", "Syria": "Siria", "Lebanon": "Líbano",
    "Sinai": "Sinaí", "Horeb": "Horeb", "Carmel": "Carmelo",
    "Hebron": "Hebrón", "Bethel": "Bet-el", "Jericho": "Jericó",
    "Bethlehem": "Belén", "Nineveh": "Nínive", "Tyre": "Tiro",
    "Sidon": "Sidón",
    # ── Pueblos / gentilicios ────────────────────────────────────────────────
    "Hivite[s]": "heveos", "Hivites": "heveos", "Hivite": "heveo",
    "Hahiroth": "Hahirot", "Hittites": "heteos", "Hittite": "heteo",
    "Amorites": "amorreos", "Amorite": "amorreo",
    "Canaanites": "cananeos", "Canaanite": "cananeo",
    "Perizzites": "ferezeos", "Perizzite": "ferezeo",
    "Jebusites": "jebuseos", "Jebusite": "jebuseo",
    "Girgashites": "gergeseos", "Girgashite": "gergeseo",
    "Bethlehemite": "belemita", "Bethlehemites": "belemitas",
    # ── Personas ─────────────────────────────────────────────────────────────
    "Zadok": "Sadoc",
    "Hiram": "Hiram",
    "Artaxerxes": "Artajerjes",
    "Joab": "Joab",
    "Eleazar": "Eleazar",
    "Amariah": "Amarías",
    "Azariah": "Azarías",
    "Jonathan": "Jonatán",
    "Asa": "Asa",
    "Ish-bosheth": "Is-boset",
    "Shimei": "Simei",
    "Johanan": "Johanán",
    "Tiglath-pileser": "Tiglat-pileser",
    "Elkanah": "Elcaná",
    "Jeremiah": "Jeremías",
    "Jehoshaphat": "Josafat",
    "Yahweh": "Yahvé",
    "Jehoash": "Joás",
    "Jonah": "Jonás",
    "Ahitub": "Ahitob",
    "Obadiah": "Abdías",
    "Jozabad": "Jozabad",
    "Ahimelech": "Ahimelec",
    "Esarhaddon": "Esarhadón",
    "Phineas": "Finees", "Phinehas": "Finees",
    "Abinadab": "Abinadab", "Abiathar": "Abiatar",
    "Hushai": "Husai", "Ahithophel": "Ahitofel",
    "Bathsheba": "Betsabé", "Abishag": "Abisag",
    "Adonijah": "Adonías", "Benaiah": "Benaías",
    "Gehazi": "Giezi", "Elisha": "Eliseo",
    "Hezekiah": "Ezequías", "Sennacherib": "Senaquerib",
    "Manasseh": "Manasés", "Josiah": "Josías",
    "Jehoiakim": "Joacim", "Jehoiachin": "Joaquín",
    "Zedekiah": "Sedequías", "Gedaliah": "Godolías",
    "Nehemiah": "Nehemías", "Ezra": "Esdras",
    "Zerubbabel": "Zorobabel", "Jeshua": "Josué",
    "Zechariah": "Zacarías", "Haggai": "Ageo",
    "Malachi": "Malaquías", "Micaiah": "Miqueas",
    "Obadiah": "Abdías", "Nahum": "Nahúm",
    "Habakkuk": "Habacuc", "Zephaniah": "Sofonías",
    "Uzziah": "Uzías", "Jotham": "Jotam",
    "Ahaz": "Acaz", "Rezin": "Rezín",
    "Pekah": "Peca", "Hoshea": "Oseas",
    "Shalmaneser": "Salmanasar",
    # ── Lugares / ciudades ───────────────────────────────────────────────────
    "Gath": "Gat",
    "Ezion": "Esión", "Ezion-geber": "Esión-geber",
    "Bashan": "Basán",
    "Beth Shemesh": "Bet-semes", "Beth-shemesh": "Bet-semes",
    "Arabah": "Arabá",
    "Hattaavah": "Kibrot-hataavá",
    "Tel": "Tel",
    "Hazar": "Hasar",
    "Ben Hinnom": "Ben Hinón", "Hinnom": "Hinón",
    "Rimmon": "Rimón",
    "Rehob": "Rehob",
    "Shan": "Sán",
    "Dagon": "Dagón",
    "Shemesh": "Semes",
    "Shiloh": "Siló", "Gibeah": "Guibeá",
    "Mizpah": "Mispá", "Mizpeh": "Mispá",
    "Ramah": "Ramá", "Zion": "Sión",
    "Ophel": "Ofel", "Kidron": "Cedrón",
    "Hinnom": "Hinón", "Tophet": "Tofet",
    "Carchemish": "Carquemis", "Hamath": "Jamat",
    "Lachish": "Laquis", "Megiddo": "Meguido",
    "Jezreel": "Jezrael", "Samaria": "Samaria",
    "Peniel": "Penuel", "Mahanaim": "Mahanaim",
    "Succoth": "Sucot", "Jabbok": "Jaboc",
    "Gilgal": "Gilgal", "Shittim": "Sitín",
    "Kadesh": "Cades", "Kadesh-barnea": "Cades-barnea",
    "Beersheba": "Berseba", "Beer-sheba": "Berseba",
    "Dothan": "Dotán", "Shechem": "Siquén",
    "Tirzah": "Tirsa", "Penuel": "Penuel",
    "Gezer": "Guézer", "Aijalon": "Ayalón",
    "Azekah": "Azeca", "Adullam": "Adulam",
    "Ziklag": "Siclag", "Aphek": "Afec",
    "Ashdod": "Asdod", "Ashkelon": "Ascalón",
    "Ekron": "Ecrón", "Gaza": "Gaza",
    "Aroer": "Aroer", "Dibon": "Dibón",
    "Medeba": "Medeba", "Heshbon": "Hesbón",
    "Gilead": "Galaad",
    # ── Valores crudos con puntos (word.word) ────────────────────────────────
    # Números compuestos
    "one.hundred": "cien", "two.hundred": "doscientos",
    "three.hundred": "trescientos", "four.hundred": "cuatrocientos",
    "five.hundred": "quinientos", "six.hundred": "seiscientos",
    "seven.hundred": "setecientos", "eight.hundred": "ochocientos",
    "nine.hundred": "novecientos",
    "one.thousand": "mil", "two.thousand": "dos mil",
    "ten.thousand": "diez mil",
    # Frases nominales frecuentes
    "of.linen": "de lino",
    "the.middle": "en medio", "the.midst": "en medio",
    "the.days": "los días", "the.day": "el día",
    "the.inhabitants": "los habitantes",
    "the.multitude": "la multitud",
    "the.court": "el atrio",
    "the.wadi": "el torrente",
    "the.reign": "el reinado",
    "the.territory": "el territorio",
    "the.elders": "los ancianos",
    "the.horns": "los cuernos",
    "the.steps": "los escalones",
    "the.hands": "las manos",
    "the.servants": "los siervos",
    "the.commandments": "los mandamientos",
    "the.young.woman": "la joven",
    "a.virgin": "una virgen",
    "a.statute": "un estatuto",
    "a.foe": "un enemigo",
    "a.horse": "un caballo",
    "a.horror": "espanto",
    "of.gold": "de oro",
    "of.it": "de ello",
    "of.hosts": "de los ejércitos",
    "of.ships": "de barcos",
    "of.its.head": "de su cabeza",
    "palm.trees": "palmeras",
    "their.own": "los suyos",
    "my.own": "mío",
    "your.covenant.loyalty": "tu misericordia",
    "your.words": "tus palabras",
    "lift.up": "levanta",
    "the.utterance": "declaración",
    # Frases verbales frecuentes
    "let.it.be": "sea", "it.was": "fue", "it.became": "se volvió",
    "it.will.be": "será", "it.will.please": "plazca",
    "it.has.fallen": "ha caído", "it.is.exalted": "es exaltado",
    "he.said": "dijo", "he.was": "era", "he.did": "hizo",
    "he.says": "dice", "he.came": "vino", "he.took": "tomó",
    "he.went.up": "subió", "he.will.be": "será", "he.will.do": "hará",
    "he.had.said": "había dicho", "he.had.brought.out": "había sacado",
    "I.said": "dije", "I.saw": "vi", "I.will.turn.back": "haré volver",
    "you.will.know": "sabrás", "you.spoke": "hablaste",
    "will.listen": "escuchará",
    "they.did": "hicieron",
    # ── Más personas / nombres bíblicos ─────────────────────────────────────
    "Hannah": "Ana", "Samuel": "Samuel", "Jesse": "Isaí",
    "Jabesh": "Jabes", "Jephthah": "Jefté",
    "Nabal": "Nabal", "Abner": "Abner", "Achish": "Aquis",
    "Ebenezer": "Eben-ézer",
    "Ramathaim": "Ramataim", "Kiriath Jearim": "Quiriat-jearim",
    "Ichabod": "Icabod", "Shemeshite": "betsemita",
    "Edomite": "edomita", "Edomites": "edomitas",
    "Jebusites": "jebuseos", "Amalekites": "amalecitas",
    "Amalekite": "amalecita", "Moabite": "moabita", "Moabites": "moabitas",
    "Ammonite": "amonita", "Ammonites": "amonitas",
    "Ezel": "Ézel", "Horesh": "Hóres",
    "Bor": "Bor", "Achish": "Aquis",
    "Doeg": "Doeg", "Saul": "Saúl",
    "Abigail": "Abigail", "Ahinoam": "Ahinoam",
    "Mephibosheth": "Mefiboset", "Ziba": "Sibá",
    "Absalom": "Absalón", "Amnon": "Amnón",
    "Tamar": "Tamar", "Jonadab": "Jonadab",
    "Ittai": "Itai", "Barzillai": "Barzilai",
    "Amasa": "Amasá", "Sheba": "Sebá",
    "Araunah": "Arauna", "Ornan": "Ornán",
    "Abishai": "Abisai",
    "Elijah": "Elías", "Elisha": "Eliseo",
    "Naboth": "Nabot", "Jezebel": "Jezabel",
    "Ahab": "Acab", "Omri": "Omrí",
    "Tibni": "Tibni", "Zimri": "Zimri",
    "Baasha": "Basá", "Nadab": "Nadab",
    "Jeroboam": "Jeroboam", "Rehoboam": "Roboam",
    "Abijam": "Abiam", "Asa": "Asa",
    "Hanani": "Hananías", "Jehu": "Jehú",
    "Michal": "Mical", "Rizpah": "Rizpá",
    "Ishbosheth": "Is-boset", "Ish-bosheth": "Is-boset",
    # ── Expansión V5 (Éxodo + cola larga) ─────────────────────────────────
    "frogs": "ranas", "bands": "bandas", "hooks": "ganchos",
    "some": "algunos", "downwards": "hacia abajo", "hosts": "ejércitos",
    "enchantments": "encantamientos", "grumblings": "murmuraciones",
    "a sheep": "una oveja", "blossoms": "flores", "fire-pans": "braseros",
    "their forced": "su forzado", "work(s)": "obras", "River": "río",
    "soothsayer-priests": "sacerdotes adivinos",
    "he did": "hizo", "we will sacrifice": "sacrificaremos",
    "he will make restitution": "restituirá",
    "he will make compensation": "compensará",
    "bowls": "tazones", "sandals": "sandalias", "labor": "trabajo",
    "descendants": "descendientes", "canals": "canales", "pools": "estanques",
    "he stretched out": "extendió", "they did": "hicieron",
    "they will remain": "permanecerán", "heaps": "montones",
    "gnats": "piojos", "flies": "moscas", "hail": "granizo",
    "locusts": "langostas", "boils": "úlceras",
    "firstborn": "primogénito", "unleavened": "sin levadura",
    "leaven": "levadura", "bitter": "amargo", "staff": "vara",
    "pillar": "columna", "curtain": "cortina", "curtains": "cortinas",
    "rings": "anillos", "boards": "tablas", "bars": "barras",
    "sockets": "basas", "clasps": "broches", "covering": "cubierta",
    "screen": "pantalla", "veil": "velo", "ephod": "efod",
    "breastplate": "pectoral", "incense": "incienso",
    "atonement": "expiación", "anointing": "unción",
    "laver": "fuente", "basin": "vasija",
    "congregation": "congregación", "assembly": "asamblea",
    "plague": "plaga", "pestilence": "pestilencia",
    "darkness": "tinieblas", "manna": "maná", "quail": "codornices",
    "wilderness": "desierto", "tent": "tienda",
    "testimony": "testimonio", "tablets": "tablas",
    "calf": "becerro", "stiff-necked": "de dura cerviz",
    "cloud": "nube", "smoke": "humo", "trumpet": "trompeta",
    "male": "macho", "female": "hembra", "stranger": "extranjero",
    "strangers": "extranjeros", "sojourner": "peregrino",
    "widow": "viuda", "orphan": "huérfano", "poor": "pobre",
    "rich": "rico", "thief": "ladrón", "murderer": "homicida",
    "sorcerer": "hechicero", "sorcery": "hechicería",
    "blasphemy": "blasfemia", "idolatry": "idolatría",
    "adultery": "adulterio", "false": "falso",
    "true": "verdadero", "just": "justo", "righteous": "justo",
    "innocent": "inocente", "guilty": "culpable",
    "clean": "limpio", "unclean": "inmundo",
    "sacred": "sagrado", "profane": "profano",
    "above": "arriba", "below": "abajo", "beyond": "más allá",
    "behind": "detrás", "beside": "al lado", "between": "entre",
    "through": "a través", "toward": "hacia", "against": "contra",
    "after": "después", "until": "hasta", "since": "desde",
    "during": "durante", "near": "cerca", "far": "lejos",
    "inside": "dentro", "upon": "sobre", "across": "a través",
    "throughout": "por todo", "according": "según",
    "[will": "",
    # ── Verbos copulativos y auxiliares EN→ES ──────────────────────────────
    "is": "es", "are": "son", "were": "eran", "was": "era",
    "am": "soy", "be": "ser",
    "it is": "es", "he is": "es", "she is": "es",
    "they are": "son", "we are": "somos", "you are": "eres",
    "it was": "era", "he was": "era", "she was": "era",
    "those who": "los que", "one who": "el que",
    "who": "quien", "which": "que",
    "when": "cuando", "where": "donde",
    # ── Pronombres y determinantes sueltos ─────────────────────────────────
    "it": "", "he": "", "she": "", "they": "", "we": "", "you": "",
    "me": "", "us": "", "him": "", "her": "", "them": "",
    "his": "su", "their": "su", "our": "nuestro", "your": "tu", "my": "mi",
    "its": "su", "the": "", "a": "un", "an": "un",
    "this": "este", "that": "ese", "these": "estos", "those": "esos",
    "all": "todo", "every": "cada", "each": "cada",
    "some": "algunos", "many": "muchos", "much": "mucho", "more": "más",
    "most": "la mayoría", "other": "otro", "another": "otro",
    "also": "también", "even": "aun", "still": "aún",
    "very": "muy", "only": "solo", "just": "solo",
    "again": "otra vez", "back": "atrás", "away": "lejos",
    "here": "aquí", "there": "allí", "now": "ahora", "then": "entonces",
    "great": "grande", "small": "pequeño", "little": "pequeño",
    "new": "nuevo", "old": "viejo", "young": "joven",
    "high": "alto", "low": "bajo", "long": "largo",
    "good": "bueno", "evil": "malo", "bad": "malo",
    "first": "primero", "last": "último", "next": "siguiente",
    # ── Verbos sueltos frecuentes ──────────────────────────────────────────
    "go": "ir", "come": "ven", "take": "tomar", "give": "dar",
    "see": "ver", "know": "saber", "do": "hacer", "make": "hacer",
    "say": "decir", "speak": "hablar", "hear": "oír", "eat": "comer",
    "drink": "beber", "live": "vivir", "die": "morir",
    "set": "poner", "put": "poner", "bring": "traer",
    # ── Sustantivos frecuentes en [EN:] ────────────────────────────────────
    "clothes": "vestiduras", "works": "obras", "present": "presente",
    "its grain": "su grano", "extremities": "extremos",
    "he went": "fue", "one[s": "unos", "half": "mitad",
    "fat": "grasa", "the law": "la ley", "storehouses": "almacenes",
    "majesty": "majestad", "armies": "ejércitos",
    "ordinances": "ordenanzas", "the mountain": "el monte",
    "the house": "la casa", "the hand": "la mano",
    "the earth": "la tierra", "the people": "el pueblo",
    "the word": "la palabra", "the name": "el nombre",
    "the city": "la ciudad", "the king": "el rey",
    "the land": "la tierra", "the waters": "las aguas",
    "the heavens": "los cielos", "the nations": "las naciones",
    "the sons": "los hijos", "the children": "los hijos",
    "the voice": "la voz", "the face": "el rostro",
    "the eyes": "los ojos", "the mouth": "la boca",
    "the sword": "la espada", "the blood": "la sangre",
    "the fire": "el fuego", "the way": "el camino",
    "the door": "la puerta", "the head": "la cabeza",
    "the feet": "los pies", "the god": "el dios",
    "the priests": "los sacerdotes", "the temple": "el templo",
    "the altar": "el altar", "the throne": "el trono",
    "the river": "el río", "the sea": "el mar",
    "the field": "el campo", "the tree": "el árbol",
    "the stone": "la piedra", "the wall": "el muro",
    "forever": "para siempre", "together": "juntos",
    # ── Más sustantivos comunes faltantes ──────────────────────────────────
    "sacks": "costales", "kindred": "parentela", "mistress": "señora",
    "dawn": "alba", "households": "familias", "daughter-in-law": "nuera",
    "your households": "vuestras familias", "your little": "vuestros niños",
    "his foreskin": "su prepucio", "your only": "tu único",
    "the hip nerve": "el nervio del muslo",
    "one[s]": "unos", "ones": "unos",
    "nurse": "nodriza", "maidens": "doncellas", "maid": "sierva",
    "concubine": "concubina", "concubines": "concubinas",
    "steward": "mayordomo", "governor": "gobernador",
    "interpreter": "intérprete", "divination": "adivinación",
    "famine": "hambruna", "plenty": "abundancia",
    "prison": "prisión", "dungeon": "calabozo", "pit": "pozo",
    "wages": "salario", "dowry": "dote", "gift": "regalo",
    "sign": "señal", "wonder": "prodigio", "miracle": "milagro",
    "vision": "visión", "dream": "sueño",
    "oath": "juramento", "vow": "voto", "pledge": "prenda",
    "grain": "grano", "food": "alimento", "bread": "pan",
    "wine": "vino", "oil": "aceite", "milk": "leche", "honey": "miel",
    "fruit": "fruto", "seed": "semilla", "tree": "árbol",
    "vine": "vid", "fig": "higuera", "olive": "olivo",
    "flocks": "rebaños", "herds": "manadas", "cattle": "ganado",
    "donkeys": "asnos", "camels": "camellos", "horses": "caballos",
    "oxen": "bueyes", "lamb": "cordero", "lambs": "corderos",
    "goats": "cabras", "goat": "cabra",
    "birds": "aves", "fish": "peces", "serpent": "serpiente",
    "silver": "plata", "gold": "oro", "iron": "hierro",
    "copper": "cobre", "bronze": "bronce",
    "stone": "piedra", "stones": "piedras", "rock": "roca",
    "wall": "muro", "walls": "muros", "gate": "puerta",
    "gates": "puertas", "tower": "torre", "fortress": "fortaleza",
    "people": "pueblo", "peoples": "pueblos",
    "nations": "naciones", "nation": "nación",
    "tribe": "tribu", "tribes": "tribus",
    "king": "rey", "kings": "reyes", "queen": "reina",
    "prince": "príncipe", "princes": "príncipes",
    "captain": "capitán", "chief": "jefe",
    "servant": "siervo", "servants": "siervos",
    "slave": "esclavo", "slaves": "esclavos",
    "priest": "sacerdote", "priests": "sacerdotes",
    "prophet": "profeta", "prophets": "profetas",
    "angel": "ángel", "angels": "ángeles",
    "spirit": "espíritu", "soul": "alma", "souls": "almas",
    "word": "palabra", "words": "palabras",
    "name": "nombre", "names": "nombres",
    "voice": "voz", "song": "cántico", "prayer": "oración",
    "praise": "alabanza", "blessing": "bendición",
    "curse": "maldición", "sin": "pecado",
    "judgment": "juicio", "justice": "justicia",
    "mercy": "misericordia", "grace": "gracia",
    "truth": "verdad", "faithfulness": "fidelidad",
    "strength": "fuerza", "power": "poder", "glory": "gloria",
    "wisdom": "sabiduría", "understanding": "entendimiento",
    "knowledge": "conocimiento",
    "life": "vida", "death": "muerte", "blood": "sangre",
    "war": "guerra", "peace": "paz", "battle": "batalla",
    "sword": "espada", "bow": "arco", "shield": "escudo",
    "spear": "lanza", "arrow": "flecha", "arrows": "flechas",
    "mouth": "boca", "eyes": "ojos", "face": "rostro",
    "hand": "mano", "hands": "manos", "foot": "pie", "feet": "pies",
    "head": "cabeza", "heart": "corazón", "bone": "hueso",
    "bones": "huesos", "flesh": "carne", "body": "cuerpo",
    "tears": "lágrimas", "anger": "ira",
    "day": "día", "days": "días", "night": "noche", "nights": "noches",
    "morning": "mañana", "evening": "tarde",
    "year": "año", "years": "años", "month": "mes", "months": "meses",
    "time": "tiempo", "times": "veces", "season": "estación",
    "water": "agua", "waters": "aguas",
    "heaven": "cielo", "heavens": "cielos",
    "earth": "tierra", "dust": "polvo",
    "mountain": "monte", "mountains": "montes",
    "river": "río", "rivers": "ríos",
    "sea": "mar", "seas": "mares",
    "light": "luz", "sun": "sol", "moon": "luna", "stars": "estrellas",
    "cloud": "nube", "clouds": "nubes",
    # ── Más frases verbales dotted ─────────────────────────────────────────
    "he.saw": "vio", "she.bore": "dio a luz", "he.was.born": "nació",
    "the.nakedness": "la desnudez", "they.saw": "vieron",
    "may.they.bow.down": "que se inclinen",
    "you.will.die": "morirás", "you.will.eat": "comerás",
    "you.were.taken": "fuiste tomado", "he.fathered": "engendró",
    "he.died": "murió", "you.will.put": "pondrás",
    "they.increased": "se multiplicaron", "they.swarmed": "enjambraron",
    "long.ago": "hace mucho", "they.were.covered": "fueron cubiertos",
    "of.the.descendants": "de los descendientes",
    "he.commanded": "mandó", "he.called": "llamó", "he.sent": "envió",
    "he.built": "edificó", "he.knew": "conoció", "he.loved": "amó",
    "he.brought": "trajo", "he.gave": "dio", "he.made": "hizo",
    "he.found": "halló", "he.put": "puso", "he.set": "puso",
    "he.came.out": "salió", "he.went.out": "salió",
    "he.went.down": "descendió", "he.returned": "regresó",
    "he.heard": "oyó", "he.answered": "respondió",
    "he.struck": "golpeó", "he.killed": "mató",
    "he.ate": "comió", "he.drank": "bebió",
    "he.blessed": "bendijo", "he.cursed": "maldijo",
    "he.feared": "temió", "he.worshipped": "adoró",
    "she.said": "dijo", "she.called": "llamó", "she.saw": "vio",
    "they.came": "vinieron", "they.went": "fueron",
    "they.said": "dijeron", "they.found": "hallaron",
    "they.took": "tomaron", "they.gave": "dieron",
    "they.made": "hicieron", "they.built": "edificaron",
    "they.killed": "mataron", "they.ate": "comieron",
    "I.will.make": "haré", "I.will.give": "daré",
    "I.will.bring": "traeré", "I.will.send": "enviaré",
    "I.will.put": "pondré", "I.will.set": "pondré",
    "I.am": "yo soy", "you.are": "tú eres",
    "he.is": "él es", "they.are": "ellos son",
    "it.is": "es", "there.is": "hay", "there.are": "hay",
    "there.was": "había", "there.were": "había",
}


# Detecta valores crudos en inglés con puntos: one.hundred, of.linen, let.it.be...
_PAT_DOTTED = re.compile(r"^[a-zA-Z][a-zA-Z]*(?:\.[a-zA-Z]+)+$")


def extract_en(val: str) -> str | None:
    v = val.strip()
    m = re.match(r"^\[EN:(.*)\]$", v)
    if m:
        inner = m.group(1).strip()
        inner = inner.strip("[]").strip()
        return inner
    m2 = re.match(r"^\[(.*)\]$", v)
    if m2:
        inner = m2.group(1).strip()
        inner = inner.strip("[]").strip()
        return inner
    if _PAT_DOTTED.match(v):
        return v
    return None


def build_strong_es() -> dict[str, str]:
    """Glosa ES más frecuente para cada Strong en todo el corpus."""
    strong_counts: dict[str, Counter] = defaultdict(Counter)
    for path in sorted(DATA.glob("*_final.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for v in data.get("verses", []):
            for pair in v.get("pairs", []):
                for hw in pair.get("he_words", []):
                    s = hw.get("strongs", "")
                    es = (hw.get("es") or "").strip()
                    if s and es and not es.startswith("["):
                        strong_counts[s][es] += 1
    return {s: c.most_common(1)[0][0] for s, c in strong_counts.items() if c}


def build_user_lookups(book: str):
    """Construye dos mapas: contexto (posición exacta) y global (Strong+morph)."""
    reg = load_registry()
    ctx_map: dict[tuple, str] = {}
    glob_map: dict[str, str] = {}

    for r in reg.get("contexto", []):
        m = r.get("match") or {}
        if m.get("role") != "stem":
            continue
        if m.get("book") == book:
            key = (m.get("chapter"), m.get("verse"), m.get("pairIdx"), m.get("hwIdx"))
            ctx_map[key] = r.get("after", {}).get("es", "")

    for r in reg.get("global", []):
        m = r.get("match") or {}
        if m.get("role") != "stem":
            continue
        s = m.get("strongs", "")
        if s:
            glob_map[s] = r.get("after", {}).get("es", "")

    return ctx_map, glob_map


def process_book(slug: str, apply: bool, no_backup: bool = False):
    path = DATA / f"{slug}_final.json"
    if not path.exists():
        raise SystemExit(f"No existe {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    verses = data.get("verses", [])

    strong_es = build_strong_es()
    ctx_map, glob_map = build_user_lookups(slug)
    _en_lower = {k.lower(): v for k, v in EN_ES_TABLE.items()}

    changes: list[tuple] = []
    pending: list[tuple] = []
    counts = Counter()

    for v in verses:
        ch, vs = v.get("chapter"), v.get("verse")
        for pi, pair in enumerate(v.get("pairs", [])):
            for hi, hw in enumerate(pair.get("he_words", [])):
                es_val = (hw.get("es") or "").strip()
                is_bracket = es_val.startswith("[")
                is_dotted = bool(_PAT_DOTTED.match(es_val))
                is_standalone_en = (
                    not is_bracket and not is_dotted and es_val
                    and (es_val.lower() in _en_lower)
                    and not any(c in es_val for c in 'áéíóúñü')
                )
                if not is_bracket and not is_dotted and not is_standalone_en:
                    continue
                # No tocar si fue editado manualmente por el usuario
                if hw.get("es_source") in ("glosa_personal", "glosa_global"):
                    continue

                if is_standalone_en:
                    en_key = es_val
                else:
                    en_key = extract_en(es_val)
                    if en_key is None:
                        continue

                strongs = hw.get("strongs", "")
                he_form = hw.get("he_form", "")
                he_morph = hw.get("he_morph", "")
                new_es = None
                source = ""

                # 1. Regla de contexto del usuario
                ctx_key = (ch, vs, pi, hi)
                if ctx_key in ctx_map:
                    new_es = ctx_map[ctx_key]
                    source = "usuario_contexto"

                # 2. Regla global del usuario (por Strong)
                if new_es is None and strongs and strongs in glob_map:
                    new_es = glob_map[strongs]
                    source = "usuario_global"

                # 3. Corpus (mismo Strong)
                if new_es is None and strongs and strongs in strong_es:
                    new_es = strong_es[strongs]
                    source = "corpus_strong"

                # 4. Tabla EN→ES — busca clave exacta, con espacios, y lowercase
                if new_es is None:
                    for lookup in (en_key, en_key.replace(".", " "), en_key.lower(),
                                   en_key.lower().replace(".", " ")):
                        if lookup in EN_ES_TABLE:
                            new_es = EN_ES_TABLE[lookup]
                            source = "tabla_en_es"
                            break
                        if lookup.lower() in _en_lower:
                            new_es = _en_lower[lookup.lower()]
                            source = "tabla_en_es"
                            break

                # 5. Nombre propio → usar el valor EN directamente (si no está en tabla).
                _VERB_STARTS = ("I ", "He ", "She ", "They ", "We ", "You ",
                                "I'", "He'", "She'")
                if new_es is None and en_key and en_key[0].isupper():
                    is_nprop = (he_morph or "").startswith("NPROP")
                    is_verb_phrase = any(en_key.startswith(v) for v in _VERB_STARTS)
                    if is_nprop or (not is_verb_phrase and not is_standalone_en):
                        new_es = en_key
                        source = "nombre_propio"

                if new_es is not None:
                    hw["es"] = new_es
                    changes.append((f"{ch}:{vs}", pi, hi, source,
                                    he_form, he_morph, strongs, es_val, new_es))
                    counts[source] += 1
                else:
                    pending.append((f"{ch}:{vs}", pi, hi,
                                    he_form, he_morph, strongs, es_val, en_key))

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    report = DATA / f"_restaurar_report_{slug}.csv"
    with open(report, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref", "pairIdx", "hwIdx", "fuente", "he_form", "he_morph",
                    "strongs", "antes", "despues"])
        for row in changes:
            w.writerow(row)

    pend_path = DATA / f"_restaurar_pendiente_{slug}.csv"
    with open(pend_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ref", "pairIdx", "hwIdx", "he_form", "he_morph",
                    "strongs", "valor_actual", "en_key"])
        for row in pending:
            w.writerow(row)

    print(f"== Restaurar EN: {slug} ==")
    print(f"  RESUELTOS: {len(changes)}")
    for k in sorted(counts):
        print(f"    {k:20s}: {counts[k]}")
    print(f"  PENDIENTES: {len(pending)}")
    print(f"  reporte cambios : {report}")
    print(f"  reporte pendientes: {pend_path}")

    if apply:
        if not no_backup:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bak = BACKUP_DIR / f"{slug}_en_{ts}.json"
            bak.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"  respaldo: {bak}")
        atomic_write_json(path, data, separators=(",", ":"))
        print("  APLICADO.")
    else:
        print("  DRY-RUN. Usa --apply para escribir los cambios.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-backup", action="store_true",
                    help="No crear respaldo (uso en pipeline run_motors)")
    args = ap.parse_args()
    process_book(args.book, args.apply, args.no_backup)


if __name__ == "__main__":
    main()
