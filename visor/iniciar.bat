@echo off
chcp 65001 >nul
title Servidor interlineal CATSS Genesis - lanzador

echo ============================================
echo  Servidor interlineal CATSS - Genesis
echo ============================================
echo.

REM 1. Verificar que Python este disponible
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no esta en el PATH del sistema.
    echo Instala Python desde https://python.org/downloads o agrega
    echo C:\Users\pik_y\AppData\Local\Python\bin al PATH del usuario.
    echo.
    pause
    exit /b 1
)

REM 2. Comprobar si el servidor ya esta corriendo en el puerto 7080
netstat -an | findstr ":7080 " | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:7080/api/health', timeout=2); assert b'traduccion' in r.read()" >nul 2>&1
    if %errorlevel%==0 (
        echo [OK] El servidor TRADUCCION ya esta corriendo en el puerto 7080.
        echo Abriendo navegador...
        start "" "http://localhost:7080"
        timeout /t 2 /nobreak >nul
        exit /b 0
    )
    echo [ERROR] Puerto 7080 ocupado sin API de guardado. Cierra el servidor antiguo.
    echo         Luego ejecuta iniciar.bat de nuevo.
    pause
    exit /b 1
)

REM 3. Arrancar el servidor en una VENTANA SEPARADA que no bloquea esta consola
echo Arrancando servidor en ventana nueva...
start "Servidor CATSS (cerrar con X para detener)" cmd /k "cd /d ""%~dp0"" && python servidor.py"

REM 4. Esperar a que la API responda (max ~20 segundos)
echo Esperando que el servidor responda...
set /a tries=0
:wait_loop
ping 127.0.0.1 -n 2 >nul
python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:7080/api/health', timeout=2); assert b'traduccion' in r.read()" >nul 2>&1
if %errorlevel%==0 goto server_ready
set /a tries+=1
if %tries% lss 10 goto wait_loop

echo [AVISO] El servidor tardo en responder. Revisa la ventana "Servidor CATSS".
goto open_browser

:server_ready
echo [OK] Servidor listo en http://localhost:7080
goto open_browser

:open_browser
echo Abriendo navegador...
start "" "http://localhost:7080"
echo.
echo ============================================
echo Esta ventana se cerrara en 3 segundos.
echo El servidor sigue corriendo en su propia ventana.
echo ============================================
ping 127.0.0.1 -n 4 >nul
exit /b 0
