# BIBLIA2027

Biblia interlineal **Hebreo (Texto Masorético, base Macula) / Griego LXX / Español**.

- Hebreo consonántico: 100% Texto Masorético.
- Capa griega: Septuaginta (LXX) alineada palabra por palabra cuando hay correspondencia.
- Glosas en español por token.
- Generado: 2026-06-09T15:10:32
- Libros: 39  ·  Versos: 23,211  ·  Tokens: 469,387

## Estructura

```
BIBLIA2027/
  index.json              Manifiesto: lista de libros, totales y esquema de datos.
  README.md               Este archivo.
  books/NN_slug.json      Un archivo por libro (p. ej. 01_genesis.json).
  biblia_completa.json    Toda la Biblia en un único archivo.
```

## Cómo leerla

**Web (recomendado):** lee `index.json`, muestra la lista de `books`, y carga el
archivo del libro (`book.file`) solo cuando el usuario lo abra.

**Motor / script (carga única):** lee `biblia_completa.json` → `data.books` es un
arreglo de libros en orden canónico (1..39).

## Esquema de un libro

```json
{
  "book_num": 1,
  "book_name": "Génesis",
  "slug": "genesis",
  "chapters_count": 50,
  "verses_count": 1533,
  "chapters": {
    "1": {
      "1": { "raw": "…", "tokens": [ { "num":"1", "orig":"…", "morphs":"…",
                                         "strongs":"…", "es":"…", "gr":"…" } ] }
    }
  }
}
```

### Campos de cada token
| campo     | significado |
|-----------|-------------|
| `num`     | posición dentro del verso (1-based) |
| `orig`    | forma original (hebreo vocalizado, o griego en adiciones) |
| `morphs`  | código morfológico (opcional) |
| `strongs` | número Strong (opcional) |
| `es`      | glosa en español (opcional) |
| `gr`      | palabra/frase griega LXX alineada (opcional) |
| `notrans` | `"s/t"` = sin traducción española asignada |
| `lxx_omit`| `true` = la LXX omite esta palabra hebrea |

### Adiciones LXX
Versos sin equivalente hebreo (p. ej. cánticos griegos de Daniel) aparecen con la
clave `"<ver>_add"`:
```json
"56_add": { "is_lxx_add": true, "lxx_add_label": "3:56 ADD+ LXX",
             "gr_text": "…", "token_count": 50 }
```
