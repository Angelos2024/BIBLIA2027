@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Cerrando servidor anterior en el puerto 7080 (si lo hay)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 7080 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
echo Iniciando servidor...
start "BIBLIA2027 servidor" python visor\servidor.py
echo.
echo Servidor reiniciado en http://localhost:7080/  (recarga la pagina con Ctrl+F5)
timeout /t 2 >nul
