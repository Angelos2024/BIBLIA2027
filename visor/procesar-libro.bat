@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Procesar Libro - Motores Interlineales
color 0A

echo.
echo  ========================================================
echo     PROCESADOR DE LIBROS - MOTORES COMPLETOS
echo.
echo     Motor 1: Hebreo (Macula)
echo     Motor 2: Morfologia (dotted)
echo     Motor 3: Griego LXX (CATSS)
echo     Motor 4: Espanol (glosas)
echo     + Limpieza + Snapshot + Auditoria
echo  ========================================================
echo.

echo  Libros disponibles:
echo    genesis, exodo, levitico, numeros, deuteronomio
echo    josue, jueces, rut, 1_samuel, 2_samuel
echo    1_reyes, 2_reyes, 1_cronicas, 2_cronicas
echo    esdras, nehemias, ester, job, salmos
echo    proverbios, eclesiastes, cantares
echo    isaias, jeremias, lamentaciones, ezequiel
echo    daniel, oseas, joel, amos, abdias
echo    jonas, miqueas, nahum, habacuc, sofonias
echo    hageo, zacarias, malaquias
echo.

set /p BOOK="  Escribe el libro a procesar: "
if "%BOOK%"=="" goto :eof

set FORCE_FLAG=
if /i "%BOOK%"=="genesis" (
    echo.
    set /p FORCEYN="  Genesis: procesar capitulos 1-15 tambien? (s/n) [n]: "
    if /i "!FORCEYN!"=="s" set FORCE_FLAG=--force
)

echo.
echo  ========================================================
echo    Procesando: %BOOK%
echo  ========================================================
echo.

cd /d "%~dp0scripts"
python run_motors.py --book %BOOK% %FORCE_FLAG%

echo.
echo  ========================================================
echo    FINALIZADO
echo  ========================================================
echo.
pause
