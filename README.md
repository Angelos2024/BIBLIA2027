# Génesis 1–28 · visor interlineal (solo lectura)

Visor estático de cinco capas (hebreo MT · morfología · español · LXX · samaritano).
**Sin edición.** Capítulos **1–28**.

## Ver online

https://angelos2024.github.io/BIBLIA2027/

## Controles (defaults)

- **Samaritano** y **LXX** activos
- **Morfología** desactivada (el check sigue disponible)

## Actualizar el sitio (desde la máquina de trabajo)

Tras armar capas / corregir en el editor local:

1. Doble clic en `BIBLIA_samaritano\Publicar_visor_pages.bat`  
   (exporta caps 1–28 → este repo y deja el commit listo)
2. Tú haces el push:

```bash
cd %USERPROFILE%\Documents\GitHub\BIBLIA2027
git push
```

Pages se reconstruye solo en unos segundos.

## Abrir en local

```bash
python servir.py
```

http://127.0.0.1:8090/
