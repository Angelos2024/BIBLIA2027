# Interlineal CATSS · Génesis — Prototipo

Visor interlineal hebreo–griego de Génesis, construido sobre el archivo
`01.Genesis.par` del CATSS (Universidad de Pensilvania).

## Estructura del proyecto

```
TRADUCCION/
├── data/
│   └── genesis.json        ← Generado por el parser
├── scripts/
│   ├── parse_genesis.py    ← Parser principal (inspirado en codykingham/CATSS_parsers)
│   └── requirements.txt    ← pip install -r requirements.txt
├── index.html              ← Visor interlineal (diseño tomado de angelos)
├── logo.png
├── iniciar.bat             ← Doble clic para iniciar el servidor
└── README.md
```

## Cómo usar

### 1. Instalar dependencias Python (solo una vez)

```powershell
pip install -r scripts/requirements.txt
```

### 2. Regenerar el JSON (si cambia el .par)

```powershell
python scripts/parse_genesis.py
```

### 3. Iniciar el visor

Doble clic en `iniciar.bat`, o desde terminal:

```powershell
python -m http.server 7080 --directory "C:\Users\pik_y\Documents\TRADUCCION"
```

Luego abrir: **http://localhost:7080**

> El archivo `index.html` **no funciona abriéndolo directamente** desde el
> explorador de archivos (file://) porque fetch() está bloqueado por CORS.
> Siempre usar el servidor local.

## Fuentes de datos

| Dato | Fuente |
|------|--------|
| Alineación hebreo–LXX | CATSS `.par` · ccat.sas.upenn.edu |
| Transliteración ASCII → Unicode | Tabla CCAT interna |
| Beta Code → Unicode griego | `greek-utils==0.2` (pip) |
| Lógica de parsing | Inspirado en [codykingham/CATSS_parsers](https://github.com/codykingham/CATSS_parsers) |
| Diseño visual | Adaptado de `angelos` (Torah con Yeshúa) |

## Limitaciones del prototipo

- **Sin puntos vocálicos** en hebreo: el formato `.par` solo tiene consonantes (transliteración CCAT).
- **Sin morfología detallada**: se muestra análisis de prefijos básico (VAV.CONJ, ART, PREP.B…).
- **Sin glosas en español**: requiere un lexicón adicional (diccionario_unificado.json de angelos).
- **Solo Génesis**: es un prototipo; el resto del AT requiere los demás archivos `.par`.

## Próximos pasos sugeridos

1. Añadir archivo morfológico del CATSS para etiquetas `SUBS.M.PL.A`, `VERB.QAL.PERF` etc.
2. Conectar diccionario hebreo de angelos para glosas en español.
3. Procesar todos los libros del AT (`.par` files disponibles en `catss-par/`).
